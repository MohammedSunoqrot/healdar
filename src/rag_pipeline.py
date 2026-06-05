"""
Healdar RAG Pipeline

Arabic query flow (two-model approach for maximum quality):
  1. Translate Arabic question → English  (8B model, fast)
  2. Retrieve top-5 English chunks from ChromaDB
  3. Generate answer in English            (8B model, proven quality)
  4. Translate English answer → Arabic     (70B model, excellent quality)

English query flow:
  1. Retrieve top-5 English chunks from ChromaDB
  2. Generate answer in English            (8B model)
"""

import os
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from groq import Groq

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
VECTORSTORE  = PROJECT_ROOT / "data" / "processed" / "vectorstore"
ENV_FILE     = PROJECT_ROOT / ".env"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
COLLECTION_NAME  = "regradar"
EMBED_MODEL      = "all-MiniLM-L6-v2"
GROQ_MODEL       = "llama-3.1-8b-instant"       # fast model for English Q&A
GROQ_MODEL_LARGE = "llama-3.3-70b-versatile"    # high-quality model for Arabic translation
TOP_K            = 5

# ---------------------------------------------------------------------------
# Jurisdiction alias → actual ChromaDB values
# The vectorstore uses folder names as jurisdiction tags.
# These aliases let callers use short, friendly names.
# ---------------------------------------------------------------------------
JURISDICTION_MAP: dict[str, list[str]] = {
    "eu":    ["EU_MDR_MDCG"],
    "sfda":  ["SFDA"],
    "ksa":   ["SFDA", "KSA_SDAIA"],
    "qatar": ["Qatar_MCIT", "Qatar_MOPH", "Qatar_NCSA"],
    "uae":   ["UAE_DHA_Dubai", "UAE_DoH_AbuDhabi", "UAE_National"],
    "fda":   ["USA_FDA"],
    "usa":   ["USA_FDA"],
    "all":   [],   # empty = no filter applied
}

# ---------------------------------------------------------------------------
# Logging — suppress noisy HuggingFace HTTP logs
# ---------------------------------------------------------------------------

# HF_HUB_OFFLINE=1 is set by run.bat / run.sh for local runs where the model
# is already cached. On HuggingFace Spaces the var is absent so the model can
# be downloaded on cold start — do NOT set a default here.

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------
@dataclass
class RAGAnswer:
    question:    str
    answer:      str
    sources:     list[dict] = field(default_factory=list)
    no_context:  bool = False
    question_en: str = ""   # English version used for retrieval (= question for English queries)
    answer_en:   str = ""   # English answer before Arabic translation (for history context)

    def print(self) -> None:
        """Pretty-print the answer to stdout."""
        print("\n" + "=" * 65)
        print(f"  Q: {self.question}")
        print("=" * 65)
        if self.no_context:
            print("  [No relevant context found in the vectorstore]")
        print(f"\n{self.answer}")
        if self.sources:
            print("\n--- Sources ---")
            seen = set()
            for s in self.sources:
                key = (s["filename"], s["page_number"])
                if key in seen:
                    continue
                seen.add(key)
                print(f"  • {s['filename']}  |  {s['jurisdiction']}  |  p.{s['page_number']}")
        print("=" * 65 + "\n")


# ---------------------------------------------------------------------------
class RateLimitError(Exception):
    """Raised when Groq returns a 429 / rate-limit response."""


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------
class HealdarRAG:
    """
    Wraps ChromaDB retrieval + Groq generation into a single ask() call.
    Instantiate once and reuse — both the embedding model and the Groq
    client are loaded at __init__ time.
    """

    def __init__(self) -> None:
        # Load GROQ_API_KEY from .env at project root
        load_dotenv(ENV_FILE)
        api_key = os.getenv("GROQ_API_KEY")

        # Streamlit Cloud stores secrets in st.secrets — try it as a fallback
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GROQ_API_KEY")
            except Exception:
                pass

        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not found. Set it in .env, "
                "as an environment variable, or in .streamlit/secrets.toml."
            )

        # Embedding function — must match what embed.py used
        self._ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

        # ChromaDB persistent client
        if not VECTORSTORE.exists():
            raise FileNotFoundError(
                f"Vectorstore not found at {VECTORSTORE}\n"
                "Run src/embed.py first."
            )
        client = chromadb.PersistentClient(path=str(VECTORSTORE))
        self._collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
        )

        # Groq client
        self._groq = Groq(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ask(
        self,
        question: str,
        jurisdiction: str = "all",
        history: Optional[list[dict]] = None,
    ) -> RAGAnswer:
        """
        history: optional list of recent turns, each a dict with keys
                 'question_en' and 'answer_en' (English text only).
                 Used to provide context for follow-up questions.
        """
        """
        Run a full RAG query.

        Args:
            question:     Natural-language question from the user.
            jurisdiction: One of the keys in JURISDICTION_MAP, or 'all'.

        Returns:
            RAGAnswer dataclass with answer text and source metadata.
        """
        jurisdiction = jurisdiction.lower().strip()
        if jurisdiction not in JURISDICTION_MAP:
            valid = ", ".join(sorted(JURISDICTION_MAP.keys()))
            raise ValueError(
                f"Unknown jurisdiction '{jurisdiction}'. Valid options: {valid}"
            )

        # Step 1: Build ChromaDB where-filter
        where_filter = self._build_filter(jurisdiction)

        # Step 2: Arabic detection + query translation
        in_arabic    = self._is_arabic(question)
        question_en  = self._translate_to_english(question) if in_arabic else question

        # Step 3: For follow-up questions, reformulate into a standalone query
        #   so ChromaDB retrieval works well even for short/pronoun-heavy questions.
        search_query = (
            self._maybe_reformulate(question_en, history)
            if history else question_en
        )

        # Step 4: Retrieve top-K relevant chunks (always with an English query)
        chunks = self._retrieve(search_query, where_filter)

        if not chunks:
            return RAGAnswer(
                question=question,
                answer="I could not find relevant information in the regulatory documents for this query.",
                no_context=True,
                question_en=question_en,
            )

        # Step 5: Generate answer in English, with conversation history for context
        prompt         = self._build_prompt(question_en, chunks, history=history)
        english_answer = self._generate(prompt)

        # Step 6: Translate English answer → Arabic using the larger model
        answer_text = self._translate_to_arabic(english_answer) if in_arabic else english_answer

        # Step 7: Collect source metadata
        sources = [
            {
                "filename":     m["filename"],
                "jurisdiction": m["jurisdiction"],
                "page_number":  m["page_number"],
                "text":         m.get("text", ""),
            }
            for m in chunks
        ]

        return RAGAnswer(
            question=question,
            answer=answer_text,
            sources=sources,
            question_en=question_en,
            answer_en=english_answer,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_reformulation(question_en: str) -> bool:
        """Heuristic: short or pronoun-heavy questions are likely follow-ups."""
        if len(question_en.split()) <= 7:
            return True
        pronouns = re.compile(
            r'\b(it|this|that|they|them|these|those|the above|mentioned|'
            r'previous|same|more|elaborate|expand|what about|how about)\b',
            re.IGNORECASE,
        )
        return bool(pronouns.search(question_en))

    def _maybe_reformulate(self, question_en: str, history: list[dict]) -> str:
        """Rewrite a likely follow-up question as standalone for better retrieval."""
        if not self._needs_reformulation(question_en):
            return question_en
        last = history[-1]
        try:
            resp = self._groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Previous question: {last['question_en']}\n"
                        f"Previous answer (excerpt): {last['answer_en'][:250]}\n\n"
                        f"Follow-up question: {question_en}\n\n"
                        "Rewrite the follow-up as a complete standalone question in English. "
                        "Output only the rewritten question, nothing else."
                    ),
                }],
                temperature=0,
                max_tokens=80,
            )
            reformulated = resp.choices[0].message.content.strip()
            logger.info(f"Query reformulated: '{question_en}' → '{reformulated}'")
            return reformulated
        except Exception as exc:
            logger.warning(f"Reformulation failed, using original: {exc}")
            return question_en

    @staticmethod
    def _is_arabic(text: str) -> bool:
        """Return True if the text contains Arabic Unicode characters."""
        return bool(re.search(r'[؀-ۿ]', text))

    def _translate_to_english(self, text: str) -> str:
        """Translate an Arabic question to English (fast 8B call, minimal tokens)."""
        try:
            resp = self._groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Translate the Arabic text below into English.\n"
                        f"Output the English translation only — no explanation, no extra text.\n\n"
                        f"Arabic text: {text}\n\n"
                        f"English translation:"
                    ),
                }],
                temperature=0,
                max_tokens=200,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            if "rate limit" in str(exc).lower() or "429" in str(exc):
                raise RateLimitError("Groq rate limit reached") from exc
            logger.warning(f"Question translation failed, falling back to original: {exc}")
            return text

    def _translate_to_arabic(self, text: str) -> str:
        """
        Translate a well-formed English regulatory answer to Arabic using the 70B model.

        Citation tags [Source N] are replaced with opaque placeholders before
        translation and restored afterwards — this is more reliable than asking
        the LLM to preserve them via instructions.
        """
        # ── Step 1: Protect citation tags with placeholders the LLM won't touch ──
        placeholders: dict[str, str] = {}

        def _to_placeholder(m: re.Match) -> str:
            token = f"CITE{m.group(1)}REF"
            placeholders[token] = m.group(0)
            return token

        guarded = re.sub(r'\[Source\s*(\d+)[^\]]*\]', _to_placeholder, text, flags=re.IGNORECASE)

        # ── Step 2: Translate with the large model ──
        try:
            resp = self._groq.chat.completions.create(
                model=GROQ_MODEL_LARGE,
                messages=[{
                    "role": "user",
                    "content": (
                        "Translate the English regulatory text below into Arabic (العربية).\n\n"
                        "Rules:\n"
                        "- Keep tokens like CITE1REF, CITE2REF exactly as-is — do not translate them.\n"
                        "- Keep technical names in English: ISO, IEC, FDA, MDR, IVDR, AI Act, "
                        "SaMD, IMDRF, SFDA, DoH, MOPH, and all standard/document codes.\n"
                        "- Preserve bullet points, numbered lists, and paragraph structure.\n"
                        "- Output ONLY the Arabic translation, nothing else.\n\n"
                        f"English text:\n{guarded}\n\n"
                        "Arabic translation:"
                    ),
                }],
                temperature=0.1,
                max_tokens=2048,
            )
            translated = resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning(f"Answer translation failed, returning English: {exc}")
            return text

        # ── Step 3: Restore citation tags ──
        for token, original in placeholders.items():
            translated = translated.replace(token, original)

        return translated

    def _build_filter(self, jurisdiction: str) -> Optional[dict]:
        """
        Translate the user-facing alias into a ChromaDB metadata filter.
        Returns None when jurisdiction is 'all' (no filtering).
        """
        values = JURISDICTION_MAP[jurisdiction]

        if not values:          # "all"
            return None

        if len(values) == 1:
            # Simple equality filter
            return {"jurisdiction": values[0]}

        # Multiple possible values — use $in operator
        return {"jurisdiction": {"$in": values}}

    def _retrieve(
        self,
        question: str,
        where_filter: Optional[dict],
    ) -> list[dict]:
        """
        Query ChromaDB for the top-K chunks closest to the question embedding.
        Returns a list of metadata dicts with an extra 'text' key.
        """
        query_kwargs: dict = {
            "query_texts": [question],
            "n_results":   TOP_K,
            "include":     ["documents", "metadatas", "distances"],
        }
        if where_filter:
            query_kwargs["where"] = where_filter

        try:
            results = self._collection.query(**query_kwargs)
        except Exception as exc:
            logger.error(f"ChromaDB query failed: {exc}")
            return []

        # Flatten the nested lists ChromaDB returns (one list per query)
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]

        chunks = []
        for doc, meta in zip(documents, metadatas):
            entry = dict(meta)
            entry["text"] = doc
            chunks.append(entry)

        return chunks

    def _build_prompt(
        self,
        question: str,
        chunks: list[dict],
        history: Optional[list[dict]] = None,
    ) -> str:
        """
        Build the English-language prompt sent to Groq.
        history: last N turns as [{"question_en": ..., "answer_en": ...}].
        """
        context_blocks = []
        for i, chunk in enumerate(chunks, start=1):
            context_blocks.append(f"[Source {i}]\n{chunk['text']}")
        context = "\n\n".join(context_blocks)

        history_section = ""
        if history:
            turns = []
            for h in history[-3:]:
                snippet = h["answer_en"][:300] + ("…" if len(h["answer_en"]) > 300 else "")
                turns.append(f"User: {h['question_en']}\nAssistant: {snippet}")
            history_section = (
                "CONVERSATION HISTORY (background context only — "
                "do NOT cite sources from previous turns):\n"
                + "\n\n".join(turns)
                + "\n\n"
            )

        return (
            "You are Healdar, an expert assistant specialising in health AI regulatory "
            "frameworks across the Gulf region, Europe, and the United States.\n\n"
            f"{history_section}"
            "Answer the user's question using ONLY the CONTEXT passages provided below. "
            "When citing a source, write ONLY the short tag, e.g. [Source 1] or [Source 2]. "
            "Do NOT write filenames, paths, or any other text inside the brackets. "
            "If the context does not contain enough information to answer fully, say so clearly "
            "rather than guessing.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\n"
            "ANSWER:"
        )

    def _generate(self, prompt: str) -> str:
        """Send the prompt to Groq and return the model's response text."""
        try:
            response = self._groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1024,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            err = str(exc).lower()
            if "rate limit" in err or "429" in err or "too many" in err:
                raise RateLimitError("Groq rate limit reached") from exc
            logger.error(f"Groq API call failed: {exc}")
            raise


# ---------------------------------------------------------------------------
# Jurisdiction tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    TEST_QUESTION = (
        "What are the post-market surveillance requirements for AI medical devices?"
    )

    # One test per jurisdiction alias, in a logical order
    TESTS = [
        ("all",   TEST_QUESTION),
        ("eu",    TEST_QUESTION),
        ("sfda",  TEST_QUESTION),
        ("qatar", TEST_QUESTION),
        ("uae",   TEST_QUESTION),
        ("fda",   TEST_QUESTION),
    ]

    rag = HealdarRAG()

    total = len(TESTS)
    for idx, (jurisdiction, question) in enumerate(TESTS, start=1):
        print(f"\n>>> Test {idx}/{total}: jurisdiction = '{jurisdiction}'")
        try:
            result = rag.ask(question, jurisdiction=jurisdiction)
            result.print()
        except Exception as exc:
            print(f"  [FAILED] {exc}\n")
