"""
Healdar RAG pipeline.

English query:
  1. retrieve (hybrid dense + BM25, relevance-gated)
  2. generate the answer in English

Arabic query:
  1. translate question -> English          (small model, fast)
  2. retrieve with the English query
  3. generate the answer in English         (answer model)
  4. translate the answer -> Arabic         (large model)

The English answer is always kept alongside the Arabic one, so conversation
history and PDF export can use it.

Citation numbering is decided in exactly one place -- the passages list built
here. The prompt, RAGAnswer.sources and the UI all index into that same list,
so "[Source 3]" in the text is always the third entry in the reference list.
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import groq
from dotenv import load_dotenv
from groq import Groq

import config
import vectorstore
from retrieval import Passage, Retriever

logger = logging.getLogger(__name__)

# Suppress noisy third-party HTTP logs.
for _noisy in ("httpx", "sentence_transformers", "transformers", "huggingface_hub"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

# HF_HUB_OFFLINE=1 is set by run.bat / run.sh for local runs where the model is
# already cached. On HuggingFace Spaces the var is absent so the model can be
# downloaded on cold start -- do NOT set a default here.

# ---------------------------------------------------------------------------
# Jurisdiction alias -> the jurisdiction values stored in the vector store
# (which are the raw_docs/ folder names).
# ---------------------------------------------------------------------------
JURISDICTION_MAP: dict[str, list[str]] = {
    "eu":    ["EU_Legislation", "EU_MDCG", "EU_AI_Office"],
    # SFDA regulates the device, SDAIA governs the data and the AI itself, and
    # NHIC sets the national health-information standards. A Saudi question
    # almost always needs more than one of them.
    "sfda":  ["KSA_SFDA", "KSA_SDAIA", "KSA_NHIC"],
    "ksa":   ["KSA_SFDA", "KSA_SDAIA", "KSA_NHIC"],
    "qatar": ["Qatar_MOPH", "Qatar_MCIT", "Qatar_NCSA", "Qatar_Legislation"],
    "uae":   ["UAE_Federal", "UAE_DoH_AbuDhabi", "UAE_DHA_Dubai"],
    "fda":   ["USA_FDA"],
    "usa":   ["USA_FDA"],
    "intl":  ["INT_WHO", "INT_IMDRF"],
    "all":   [],   # empty = search everything
}

# Folder tag -> the jurisdiction a user would name. Balancing in "all" mode
# caps passages per *jurisdiction* (all of Saudi Arabia), not per regulator
# folder -- otherwise a country split across three folders gets three quotas.
_CANONICAL_JURISDICTIONS = ("eu", "sfda", "uae", "qatar", "fda", "intl")
JURISDICTION_GROUPS: dict[str, str] = {
    tag: key for key in _CANONICAL_JURISDICTIONS for tag in JURISDICTION_MAP[key]
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

# A question that names its jurisdiction ("... under the EU MDR") is about that
# jurisdiction even when the selector is left on "All". Balancing across every
# jurisdiction then capped the EU at two passages and filled the rest with FDA
# and SFDA pages -- dropping the Rule 11 pages a classification answer needs.
# Acronyms match case-sensitively so that "who" and "us" do not count.
_NAMED_JX: dict[str, re.Pattern] = {
    "eu": re.compile(
        r"(?<!\w)(?:EU|E\.U\.|MDR|IVDR|MDCG|AI Act|CE[- ]mark\w*"
        r"|(?i:european union|europe|notified bod(?:y|ies)))(?!\w)"
    ),
    "sfda": re.compile(r"(?<!\w)(?:SFDA|SDAIA|NHIC|KSA|(?i:saudi))(?!\w)"),
    "uae": re.compile(
        r"(?<!\w)(?:UAE|DoH|DHA|MOHAP"
        r"|(?i:united arab emirates|emirates|emirati|abu dhabi|dubai))(?!\w)"
    ),
    "qatar": re.compile(r"(?<!\w)(?:MOPH|MCIT|NCSA|(?i:qatar|qatari))(?!\w)"),
    "fda": re.compile(
        r"(?<!\w)(?:FDA|USA|U\.S\.|US|PMA|510\(k\)|(?i:united states|de novo))(?!\w)"
    ),
    "intl": re.compile(r"(?<!\w)(?:WHO|IMDRF|(?i:world health organi[sz]ation))(?!\w)"),
}


class HealdarError(Exception):
    """Base class for errors the UI knows how to present."""


class RateLimitError(HealdarError):
    """Groq returned 429."""


class ServiceUnavailableError(HealdarError):
    """Groq is unreachable, timed out, or returned 5xx."""


class ModelUnavailableError(HealdarError):
    """The configured model id was rejected -- usually a decommissioned model."""


class RetrievalError(HealdarError):
    """The vector store failed. Distinct from 'nothing relevant was found'."""


def _wrap_groq_error(exc: Exception) -> Exception:
    """Map a Groq SDK exception onto a Healdar error the UI can render."""
    if isinstance(exc, groq.RateLimitError):
        return RateLimitError("Groq rate limit reached")
    if isinstance(exc, (groq.APITimeoutError, groq.APIConnectionError)):
        return ServiceUnavailableError(f"Could not reach Groq: {exc}")
    if isinstance(exc, groq.APIStatusError):
        status = getattr(exc, "status_code", None)
        body = str(exc).lower()
        if status == 404 or "decommission" in body or "does not exist" in body:
            return ModelUnavailableError(str(exc))
        if status and status >= 500:
            return ServiceUnavailableError(f"Groq returned {status}")
    return exc


_CITE_GROUP = re.compile(
    r"[\[【［]\s*(Sources?\s*\d[^\]】］]*)[\]】］]", re.IGNORECASE
)


def canonical_citations(text: str) -> str:
    """
    Rewrite every citation variant to the canonical "[Source N]".

    Handles 【Source 2】 and ［Source 2］ brackets, grouped citations such as
    "[Source 1, Source 3]" or "【Source 1, 4】" (each number kept), and trailing
    detail like "[Source 2: file.pdf | p.5]" or "【Source 1†L10-L12】".
    """
    def repl(m: re.Match) -> str:
        nums: list[str] = []
        for part in re.split(r"[,;]|\band\b", m.group(1)):
            found = re.match(r"\s*(?:Sources?\s*)?(\d+)", part, re.IGNORECASE)
            if found:
                nums.append(found.group(1))
        return "".join(f"[Source {n}]" for n in dict.fromkeys(nums)) or m.group(0)

    return _CITE_GROUP.sub(repl, text)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class RAGAnswer:
    question:      str
    answer:        str
    sources:       list[dict] = field(default_factory=list)
    no_context:    bool = False
    question_en:   str = ""
    answer_en:     str = ""
    # "ok" | "weak" -- material found but a poor match | "no_match"
    quality:       str = "ok"
    best_distance: float | None = None
    # "full" | "partial" -- the model's own assessment of context sufficiency
    coverage:      str = "full"
    model:         str = ""

    @property
    def is_weak(self) -> bool:
        return self.quality == "weak" or self.coverage == "partial"

    def to_stdout(self) -> None:
        """Pretty-print to the terminal (used by the __main__ smoke test)."""
        print("\n" + "=" * 65)
        print(f"  Q: {self.question}")
        print("=" * 65)
        if self.no_context:
            print("  [No relevant context found in the vector store]")
        print(f"\n{self.answer}")
        if self.sources:
            print("\n--- Sources ---")
            for i, s in enumerate(self.sources, start=1):
                rel = s.get("relevance")
                rel_s = f"  rel={rel}" if rel is not None else ""
                print(f"  [{i}] {s['filename']} | {s['jurisdiction']} | "
                      f"p.{s['page_number']}{rel_s}")
        print(f"\n  quality={self.quality} coverage={self.coverage} model={self.model}")
        print("=" * 65 + "\n")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class HealdarRAG:
    """
    Retrieval + generation behind a single ask() call.

    Construct once and reuse: the embedding model, the vector store and the
    Groq client are all set up in __init__.
    """

    def __init__(self, *, verify_model: bool = True) -> None:
        load_dotenv(config.ENV_FILE)
        api_key = os.getenv("GROQ_API_KEY")

        # Streamlit Cloud keeps secrets in st.secrets rather than the env.
        if not api_key:
            try:
                import streamlit as st

                api_key = st.secrets.get("GROQ_API_KEY")
            except Exception:
                pass

        if not api_key:
            raise HealdarError(
                "GROQ_API_KEY not found. Set it in .env, as an environment "
                "variable, or in .streamlit/secrets.toml."
            )

        try:
            collection = vectorstore.load_collection()
        except vectorstore.VectorStoreError as exc:
            raise RetrievalError(str(exc)) from exc

        self._retriever = Retriever(collection, group_of=JURISDICTION_GROUPS)
        self._groq = Groq(
            api_key=api_key,
            timeout=config.GROQ_TIMEOUT,
            max_retries=config.GROQ_MAX_RETRIES,
        )
        self.answer_model = config.GROQ_MODEL_ANSWER

        if verify_model:
            self._verify_models()

    # ------------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------------

    def _verify_models(self) -> None:
        """
        Confirm the configured answer model still exists.

        Groq decommissions models on a published schedule; when that happens
        every query fails with the same opaque error. One tiny call at startup
        turns that into a clear, actionable message.
        """
        try:
            self._groq.chat.completions.create(
                model=self.answer_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
        except Exception as exc:
            wrapped = _wrap_groq_error(exc)
            if isinstance(wrapped, ModelUnavailableError):
                raise ModelUnavailableError(
                    f"Groq rejected the model '{self.answer_model}'. It may have "
                    "been decommissioned -- see "
                    "https://console.groq.com/docs/deprecations and set the "
                    "GROQ_MODEL_ANSWER environment variable to a current model."
                ) from exc
            # Rate limits / transient outages at startup are not fatal.
            logger.warning("Model check inconclusive: %s", wrapped)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ask(
        self,
        question: str,
        jurisdiction: str = "all",
        history: list[dict] | None = None,
    ) -> RAGAnswer:
        """
        Run one full RAG query.

        Args:
            question:     the user's question, English or Arabic.
            jurisdiction: a key of JURISDICTION_MAP.
            history:      recent turns as [{"question_en", "answer_en"}], used
                          to resolve follow-up questions.
        """
        jurisdiction = (jurisdiction or "all").lower().strip()
        if jurisdiction not in JURISDICTION_MAP:
            valid = ", ".join(sorted(JURISDICTION_MAP))
            raise ValueError(
                f"Unknown jurisdiction '{jurisdiction}'. Valid options: {valid}"
            )

        in_arabic = self._is_arabic(question)
        question_en = self._translate_to_english(question) if in_arabic else question

        search_query = (
            self._maybe_reformulate(question_en, history) if history else question_en
        )

        jx_tags = JURISDICTION_MAP[jurisdiction]
        plan_jx = jurisdiction
        if jurisdiction == "all":
            named = self._named_jurisdictions(search_query)
            if named:
                jx_tags = [tag for key in named for tag in JURISDICTION_MAP[key]]
                plan_jx = named[0] if len(named) == 1 else "all"
                logger.info("Question names %s: searching those jurisdictions", named)
        try:
            found = self._retriever.search(search_query, jx_tags)
            # Only a question that passes the relevance gate on its own is
            # worth planning for -- and planned queries must never be what
            # lets an off-topic question through.
            planned = self._plan_queries(search_query, plan_jx) if found else []
            if planned:
                found = self._retriever.search_many([search_query, *planned], jx_tags)
        except HealdarError:
            raise
        except Exception as exc:
            # An index failure is NOT "no information exists" -- say so, loudly.
            logger.error("Retrieval failed: %s", exc, exc_info=True)
            raise RetrievalError(
                "The regulatory index could not be searched. This is a system "
                "fault, not an absence of regulation."
            ) from exc

        if not found:
            return RAGAnswer(
                question=question,
                answer="No relevant material was found in the regulatory "
                       "documents for this question.",
                no_context=True,
                question_en=question_en,
                quality=found.quality,
                best_distance=found.best_distance,
                model=self.answer_model,
            )

        # One passage per source page: same-page chunks are merged so that the
        # prompt, the sources list and the UI share a single numbering scheme.
        passages = self._merge_by_page(found.passages)

        prompt = self._build_prompt(question_en, passages, history=history)
        raw_answer = self._generate(prompt)
        english_answer, coverage = self._extract_coverage(canonical_citations(raw_answer))

        answer_text = (
            self._translate_to_arabic(english_answer) if in_arabic else english_answer
        )

        return RAGAnswer(
            question=question,
            answer=answer_text,
            sources=[p.to_source_dict() for p in passages],
            question_en=question_en,
            answer_en=english_answer,
            quality=found.quality,
            best_distance=found.best_distance,
            coverage=coverage,
            model=self.answer_model,
        )

    def ask_many(
        self,
        requests: list[tuple[str, str]],
        history: list[dict] | None = None,
    ) -> list[RAGAnswer]:
        """
        Run several (question, jurisdiction) queries concurrently.

        Comparison mode used to run two full pipelines back to back -- up to
        eight serial Groq calls for an Arabic comparison. Running them in
        parallel roughly halves the wait; the Groq client is thread-safe.
        """
        if not requests:
            return []
        if len(requests) == 1:
            q, jx = requests[0]
            return [self.ask(q, jurisdiction=jx, history=history)]

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures = [
                pool.submit(self.ask, q, jurisdiction=jx, history=history)
                for q, jx in requests
            ]
            return [f.result() for f in futures]

    # ------------------------------------------------------------------
    # Language handling
    # ------------------------------------------------------------------

    _ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]")
    _LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

    @classmethod
    def _is_arabic(cls, text: str) -> bool:
        """
        True when the text is substantially Arabic.

        A ratio rather than "contains one Arabic character": a single Arabic
        quotation mark or borrowed term in an English question should not
        divert the whole query through the translation pipeline.
        """
        letters = cls._LETTER_RE.findall(text)
        if not letters:
            return False
        arabic = sum(1 for ch in letters if cls._ARABIC_RE.match(ch))
        return arabic / len(letters) >= 0.2

    def _translate_to_english(self, text: str) -> str:
        """Translate an Arabic question to English. Falls back to the original."""
        try:
            resp = self._chat(
                model=config.GROQ_MODEL_SMALL,
                content=(
                    "Translate the Arabic text below into English.\n"
                    "Output the English translation only -- no explanation.\n\n"
                    f"Arabic text: {text}\n\nEnglish translation:"
                ),
                temperature=0,
                max_tokens=300,
            )
            return resp or text
        except RateLimitError:
            raise
        except HealdarError as exc:
            logger.warning("Question translation failed, using original: %s", exc)
            return text

    def _translate_to_arabic(self, text: str) -> str:
        """
        Translate the finished English answer into Arabic with the large model.

        Citation tags are swapped for opaque placeholders first: asking a model
        to "preserve [Source 3] exactly" is unreliable, whereas an unfamiliar
        token like CITE3REF survives translation untouched. If any placeholder
        fails to come back, the translation is discarded rather than shipping
        an answer whose citations have silently vanished.
        """
        placeholders: dict[str, str] = {}

        def _to_placeholder(m: re.Match) -> str:
            token = f"CITE{m.group(1)}REF"
            placeholders[token] = m.group(0)
            return token

        guarded = config.CITATION_RE.sub(_to_placeholder, text)

        try:
            translated = self._chat(
                model=config.GROQ_MODEL_LARGE,
                content=(
                    "Translate the English regulatory text below into Arabic.\n\n"
                    "Rules:\n"
                    "- Keep tokens like CITE1REF, CITE2REF exactly as-is.\n"
                    "- Keep technical names in English: ISO, IEC, FDA, MDR, "
                    "IVDR, AI Act, SaMD, IMDRF, SFDA, SDAIA, DoH, MOPH, and all "
                    "standard and document codes.\n"
                    "- Preserve bullet points, numbered lists and paragraphs.\n"
                    "- Output ONLY the Arabic translation.\n\n"
                    f"English text:\n{guarded}\n\nArabic translation:"
                ),
                temperature=0.1,
                max_tokens=config.ANSWER_MAX_TOKENS + 600,
            )
        except RateLimitError:
            raise
        except HealdarError as exc:
            logger.warning("Answer translation failed, returning English: %s", exc)
            return text

        if not translated:
            return text

        missing = [tok for tok in placeholders if tok not in translated]
        if missing:
            logger.warning(
                "Translation dropped %d citation tag(s) %s -- keeping English.",
                len(missing), missing,
            )
            return text

        for token, original in placeholders.items():
            translated = translated.replace(token, original)
        return translated

    # ------------------------------------------------------------------
    # Follow-up questions
    # ------------------------------------------------------------------

    _DEIXIS_RE = re.compile(
        r"\b(it|its|this|that|they|them|these|those|the above|mentioned|"
        r"previous|previously|same|more|elaborate|expand|what about|how about|"
        r"and (?:in|for)|compare|instead)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _needs_reformulation(cls, question_en: str) -> bool:
        """
        Does this look like a follow-up that cannot stand on its own?

        Requires an actual back-reference. Length alone is a poor signal: a
        short question can be perfectly self-contained ("SFDA SaMD rules?"),
        and rewriting it against unrelated history makes retrieval worse, not
        better -- while costing an extra round trip.
        """
        if cls._DEIXIS_RE.search(question_en):
            return True
        # Very short AND no concrete subject to anchor on.
        words = question_en.split()
        return len(words) <= 3

    def _maybe_reformulate(self, question_en: str, history: list[dict]) -> str:
        if not history or not self._needs_reformulation(question_en):
            return question_en
        last = history[-1]
        try:
            rewritten = self._chat(
                model=config.GROQ_MODEL_SMALL,
                content=(
                    f"Previous question: {last.get('question_en', '')}\n"
                    f"Previous answer (excerpt): {last.get('answer_en', '')[:250]}\n\n"
                    f"Follow-up question: {question_en}\n\n"
                    "Rewrite the follow-up as a complete standalone question in "
                    "English. Output only the rewritten question."
                ),
                temperature=0,
                max_tokens=120,
            )
        except HealdarError as exc:
            logger.warning("Reformulation failed, using original: %s", exc)
            return question_en

        if not rewritten:
            return question_en
        logger.info("Reformulated: %r -> %r", question_en, rewritten)
        return rewritten

    @staticmethod
    def _named_jurisdictions(question_en: str) -> list[str]:
        """Jurisdiction keys the question itself names, in JURISDICTION_MAP terms."""
        return [key for key, pattern in _NAMED_JX.items() if pattern.search(question_en)]

    # Measured on three case-style questions: asking for the regulation's own
    # wording retrieves the deciding pages (MDCG 2019-11's Rule 11 section for
    # a retinal-screening classification), while asking for article numbers
    # made the model guess wrong ones ("Annex VIII Rule 3").
    _PLAN_PROMPT = (
        "You are helping search a library of official health-AI regulatory "
        "documents (EU MDR, IVDR, AI Act and MDCG guidance; US FDA guidance; "
        "Saudi SFDA, SDAIA and NHIC; UAE and Qatar regulators; WHO; IMDRF).\n\n"
        "Question{jx}: {question}\n\n"
        "Write {n} search queries, one per line, that would retrieve the "
        "passages needed to answer it. Word each query the way the regulation "
        "or guidance itself would be worded: name the regulatory concept and "
        "its deciding criteria (for example 'software intended to provide "
        "information used to take decisions with diagnostic or therapeutic "
        "purposes classification') rather than guessing article or rule "
        "numbers. Cover (1) whether the rules apply to this product, (2) the "
        "specific rule or criteria that decide the answer, and (3) guidance "
        "with worked examples. Output only the queries."
    )
    _JX_LABEL = {
        "eu": "EU", "sfda": "Saudi Arabia", "ksa": "Saudi Arabia", "uae": "UAE",
        "qatar": "Qatar", "fda": "United States (FDA)", "usa": "United States (FDA)",
        "intl": "international bodies (WHO, IMDRF)",
    }

    def _plan_queries(self, question_en: str, jurisdiction: str = "all") -> list[str]:
        """
        Ask the small model which provisions a question depends on.

        A question that describes a case ("AI software that flags diabetic
        retinopathy -- which class?") is worded nothing like the rule that
        decides it (MDR Annex VIII, Rule 11), so searching the question alone
        returned FAQ pages and the answer declined to classify. Planning is
        optional: on any failure the question is still searched on its own.
        """
        if not config.QUERY_PLANNING or config.PLANNED_QUERIES <= 0:
            return []
        try:
            label = self._JX_LABEL.get(jurisdiction)
            raw = self._chat(
                model=config.GROQ_MODEL_PLANNER,
                content=self._PLAN_PROMPT.format(
                    jx=f" (jurisdiction: {label})" if label else "",
                    n=config.PLANNED_QUERIES,
                    question=question_en,
                ),
                temperature=0,
                # gpt-oss reasons before it writes and the reasoning counts
                # against this budget: at 600 tokens the 20b model returned nothing.
                max_tokens=1500,
            )
        except Exception as exc:
            logger.warning("Query planning failed, searching the question alone: %s", exc)
            return []
        return self._parse_planned(raw, question_en)

    @staticmethod
    def _parse_planned(raw: str, question_en: str) -> list[str]:
        out: list[str] = []
        for line in (raw or "").splitlines():
            q = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
            q = q.strip().strip("\"'“”").strip()
            if 3 <= len(q) <= 300 and q.lower() != question_en.strip().lower() and q not in out:
                out.append(q)
        out = out[: config.PLANNED_QUERIES]
        if out:
            logger.info("Planned queries for %r: %s", question_en, out)
        return out

    # ------------------------------------------------------------------
    # Prompting
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_by_page(passages: list[Passage]) -> list[Passage]:
        """
        Collapse passages from the same document page into one source.

        Two chunks off the same page are the same citation as far as a reader
        is concerned, and numbering them separately makes the reference list
        look padded. Merging here -- before the prompt is built -- is what
        keeps "[Source N]" and the displayed reference list in lockstep.
        """
        merged: dict[tuple[str, int], Passage] = {}
        for p in passages:
            key = (p.filename, p.page_number)
            existing = merged.get(key)
            if existing is None:
                merged[key] = Passage(**{**p.__dict__})
                continue
            if p.text not in existing.text:
                existing.text = f"{existing.text}\n\n{p.text}"
            existing.distance = min(existing.distance, p.distance)
            existing.fused_score = max(existing.fused_score, p.fused_score)
        return list(merged.values())

    def _build_prompt(
        self,
        question: str,
        passages: list[Passage],
        history: list[dict] | None = None,
    ) -> str:
        context = "\n\n".join(
            f"[Source {i}] ({p.jurisdiction})\n{p.text}"
            for i, p in enumerate(passages, start=1)
        )

        history_section = ""
        if history:
            turns = []
            for h in history[-config.HISTORY_TURNS:]:
                answer = h.get("answer_en", "")
                snippet = answer[:300] + ("..." if len(answer) > 300 else "")
                turns.append(f"User: {h.get('question_en', '')}\nAssistant: {snippet}")
            history_section = (
                "CONVERSATION HISTORY (background only -- do NOT cite sources "
                "from previous turns):\n" + "\n\n".join(turns) + "\n\n"
            )

        return (
            "You are Healdar, an expert assistant on health-AI regulatory "
            "frameworks across the Gulf region, Europe and the United States. "
            "You help people understand the rules and apply them to their own "
            "products and situations.\n\n"
            f"{history_section}"
            "Answer the question from the CONTEXT passages below. They are your "
            "evidence: every rule, requirement, definition or classification "
            "criterion you rely on must come from them, with a citation.\n\n"
            "How to answer:\n"
            "- When the question describes a product or situation (for example "
            "'which class would this device be?' or 'does this app need "
            "approval?'), apply the rules in the passages to it. Reason it "
            "through: name each rule, show how the facts of the case meet or "
            "miss its conditions, and reach a clear conclusion, such as the most "
            "likely class. Present it as an assessment ('this would most likely "
            "be Class IIb, because ...'), not as a formal regulatory decision.\n"
            "- State the assumptions the conclusion depends on and what would "
            "change it (for example, 'if the output only informs rather than "
            "drives the clinical decision, ...').\n"
            "- You may use general regulatory knowledge to connect or interpret "
            "the passages, but never as the only basis for a specific "
            "requirement, class, deadline or article number. If the rule that "
            "decides the question is not in the passages, say so plainly, mark "
            "anything you add from memory with '(not in the retrieved "
            "documents)', and treat the conclusion as provisional.\n"
            "- If something the question needs is not in the passages, still "
            "give the best-supported answer from what is there, then say what is "
            "missing and how it could change the answer.\n\n"
            "Rules:\n"
            "- Cite with the short tag only, e.g. [Source 1]. Never put "
            "filenames, paths or page numbers inside the brackets.\n"
            "- Cite the specific source for each substantive claim and for each "
            "rule used in your reasoning.\n"
            "- Quote the regulation's own wording for requirements, and name "
            "the article, clause, rule or section number when the passage gives one.\n"
            "- Some passages may be in Arabic. Read them in Arabic, and when you "
            "rely on one, give its wording in English and mark it "
            "(translated from Arabic).\n"
            "- Formatting: write in plain prose with short paragraphs. Use "
            "simple '- ' bullet lists or '1.' numbered lists where they help. "
            "Do NOT use tables, headings, horizontal rules, or bold/italic "
            "markup; the answer is shown as plain formatted text.\n"
            "- Finish with a final line, on its own, reading exactly "
            "'COVERAGE: full' if the passages were enough to answer (including "
            "by applying their rules to the case), or 'COVERAGE: partial' if "
            "something essential was missing.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\n"
            "ANSWER:"
        )

    _COVERAGE_RE = re.compile(
        r"^\s*[*_`>\-\s]*COVERAGE\s*[:\-]\s*(full|partial|none)\b.*$",
        re.IGNORECASE | re.MULTILINE,
    )

    @classmethod
    def _extract_coverage(cls, answer: str) -> tuple[str, str]:
        """Pull the trailing COVERAGE marker off the answer. Returns (text, coverage)."""
        coverage = "full"
        # The marker belongs at the end, but a model occasionally echoes the
        # instruction earlier too -- the last occurrence is the real verdict.
        matches = list(cls._COVERAGE_RE.finditer(answer))
        match = matches[-1] if matches else None
        if match:
            found = match.group(1).lower()
            coverage = "partial" if found in {"partial", "none"} else "full"
            answer = (answer[:match.start()] + answer[match.end():])
        return answer.strip(), coverage

    # ------------------------------------------------------------------
    # Groq
    # ------------------------------------------------------------------

    def _chat(
        self,
        *,
        model: str,
        content: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """One chat completion, with Groq exceptions mapped to Healdar errors."""
        try:
            resp = self._groq.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            wrapped = _wrap_groq_error(exc)
            if wrapped is not exc:
                logger.warning("Groq call failed (%s): %s", model, wrapped)
                raise wrapped from exc
            logger.error("Groq call failed (%s): %s", model, exc)
            raise
        message = resp.choices[0].message.content
        return (message or "").strip()

    def _generate(self, prompt: str) -> str:
        return self._chat(
            model=self.answer_model,
            content=prompt,
            temperature=config.ANSWER_TEMPERATURE,
            max_tokens=config.ANSWER_MAX_TOKENS,
        )


# ---------------------------------------------------------------------------
# Smoke test: one question per jurisdiction
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    QUESTION = "What are the post-market surveillance requirements for AI medical devices?"
    rag = HealdarRAG()

    for n, jx in enumerate(["all", "eu", "sfda", "qatar", "uae", "fda"], start=1):
        print(f"\n>>> {n}/6  jurisdiction={jx!r}")
        try:
            rag.ask(QUESTION, jurisdiction=jx).to_stdout()
        except Exception as exc:
            print(f"  [FAILED] {type(exc).__name__}: {exc}\n")
