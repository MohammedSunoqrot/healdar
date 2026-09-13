"""
Healdar — retrieval.

Two retrievers over the same corpus, fused:

  dense   ChromaDB + all-MiniLM-L6-v2. Good at paraphrase and intent.
  lexical BM25 over the same chunks. Good at the exact tokens regulatory
          questions hinge on -- "Article 120", "MDS-G010", "Annex VIII",
          "Class IIb" -- which embeddings blur together.

Results are combined with Reciprocal Rank Fusion, then gated on cosine
distance so an off-topic question yields nothing instead of five irrelevant
passages the model will dutifully summarise into a confident wrong answer.

Every candidate carries a real distance, including lexical-only hits: their
stored embeddings are fetched and scored against the query vector, so the
relevance gate applies uniformly no matter which retriever surfaced a passage.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np

import config

logger = logging.getLogger(__name__)

# Tokens worth keeping whole: "mds-g010", "2017/745", "62304", "class".
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-/.][a-z0-9]+)*")


def tokenize(text: str, *, split_compounds: bool = False) -> list[str]:
    """
    Lowercase tokenizer that preserves regulatory identifiers.

    split_compounds (queries only) also emits the parts of hyphenated
    compounds, so a question about "AI-based software" shares the token "ai"
    with guidance that writes "AI". The corpus keeps compounds whole, so exact
    identifiers such as "mds-g010" stay distinctive.
    """
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        out.append(tok)
        if split_compounds and "-" in tok:
            out.extend(part for part in tok.split("-") if part)
    return out


# Acronyms users type that the source documents often spell out. Without this
# (and query-side compound splitting), "How does SFDA regulate AI-based
# Software as a Medical Device?" never reached SFDA's AI/ML guidance
# (MDS-G010), even filtered to Saudi Arabia -- and the answer went on to claim
# SFDA had no AI-specific guidance at all. With both, MDS-G010 is the top Saudi
# hit. Expanding the dense query as well cost two evaluation cases, so only
# BM25 sees the expansion.
_GLOSSARY: dict[str, str] = {
    "AI":    "artificial intelligence",
    "ML":    "machine learning",
    "SaMD":  "software as a medical device",
    "SAMD":  "software as a medical device",
    "SiMD":  "software in a medical device",
    "PCCP":  "predetermined change control plan",
    "GMLP":  "good machine learning practice",
    "PDPL":  "personal data protection law",
    "QMS":   "quality management system",
    "PMS":   "post-market surveillance",
    "CDS":   "clinical decision support",
    "LLM":   "large language model",
    "LLMs":  "large language models",
    "GenAI": "generative artificial intelligence",
    "GPAI":  "general-purpose artificial intelligence",
    "IVD":   "in vitro diagnostic",
    "IVDR":  "in vitro diagnostic regulation",
    "MDR":   "medical devices regulation",
    "UDI":   "unique device identification",
    "RWE":   "real-world evidence",
    "RWD":   "real-world data",
    "EHR":   "electronic health record",
    "HIE":   "health information exchange",
    "DPIA":  "data protection impact assessment",
}
_ACRONYM_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, _GLOSSARY), key=len, reverse=True)) + r")\b"
)


def expand_query(query: str) -> str:
    """Append the spelled-out form of each known acronym the query leaves out."""
    lower = query.lower()
    extra: list[str] = []
    for acronym in dict.fromkeys(_ACRONYM_RE.findall(query)):
        full = _GLOSSARY[acronym]
        if full not in lower and full not in extra:
            extra.append(full)
    return f"{query} ({'; '.join(extra)})" if extra else query


@dataclass
class Passage:
    """One retrieved chunk, with everything the UI and the prompt need."""
    chunk_id:     str
    text:         str
    filename:     str
    jurisdiction: str
    page_number:  int
    chunk_index:  int = 0
    distance:     float = 1.0
    dense_rank:   int | None = None
    lexical_rank: int | None = None
    fused_score:  float = 0.0

    @property
    def relevance(self) -> float:
        """Cosine distance expressed as a 0..1 similarity, for display."""
        return max(0.0, min(1.0, 1.0 - self.distance))

    def to_source_dict(self) -> dict:
        return {
            "filename":     self.filename,
            "jurisdiction": self.jurisdiction,
            "page_number":  self.page_number,
            "text":         self.text,
            "relevance":    round(self.relevance, 3),
        }


@dataclass
class RetrievalResult:
    passages: list[Passage] = field(default_factory=list)
    # "ok" | "weak" (found, but a poor match) | "no_match" (nothing relevant)
    quality:  str = "ok"
    best_distance: float | None = None

    def __bool__(self) -> bool:
        return bool(self.passages)


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class Retriever:
    """
    Wraps a Chroma collection and an optional in-memory BM25 index.

    The BM25 index is built lazily on first use from chunks.json, so importing
    this module (and running unit tests) costs nothing.
    """

    def __init__(
        self,
        collection,
        *,
        hybrid: bool | None = None,
        embedding_function=None,
        group_of: dict[str, str] | None = None,
    ) -> None:
        self._collection = collection
        # Maps a folder tag to the jurisdiction it belongs to, for balancing.
        # Unknown tags are their own group.
        self._group_of = dict(group_of or {})
        self._hybrid = config.HYBRID_SEARCH if hybrid is None else hybrid
        # Needed to score lexical-only hits against the query. Chroma exposes
        # the collection's function only as a private attribute, so accept an
        # explicit one and fall back — if neither works, hybrid search degrades
        # to dense-only rather than failing.
        self._ef = embedding_function or getattr(
            collection, "_embedding_function", None
        )
        self._bm25 = None
        self._bm25_ids: list[str] = []
        self._bm25_jx: list[str] = []
        self._bm25_ready = False

    # -- lexical index ----------------------------------------------------

    def _ensure_bm25(self) -> None:
        if self._bm25_ready:
            return
        self._bm25_ready = True          # only ever attempt once
        try:
            from rank_bm25 import BM25Okapi

            import vectorstore

            chunks = vectorstore.load_chunks()
            corpus, ids, jxs = [], [], []
            for c in chunks:
                meta = c["metadata"]
                corpus.append(tokenize(c["text"]))
                ids.append(vectorstore.make_chunk_id(meta))
                jxs.append(str(meta.get("jurisdiction", "unknown")))
            self._bm25 = BM25Okapi(corpus)
            self._bm25_ids = ids
            self._bm25_jx = jxs
            logger.info("BM25 index built over %d chunks", len(corpus))
        except Exception as exc:
            logger.warning("BM25 unavailable, using dense search only: %s", exc)
            self._bm25 = None

    # -- dense ------------------------------------------------------------

    @staticmethod
    def _where(jurisdictions: list[str]) -> dict | None:
        if not jurisdictions:
            return None
        if len(jurisdictions) == 1:
            return {"jurisdiction": jurisdictions[0]}
        return {"jurisdiction": {"$in": jurisdictions}}

    def _dense(self, query: str, jurisdictions: list[str], k: int) -> list[Passage]:
        kwargs: dict = {
            "query_texts": [query],
            "n_results":   k,
            "include":     ["documents", "metadatas", "distances"],
        }
        where = self._where(jurisdictions)
        if where:
            kwargs["where"] = where

        res = self._collection.query(**kwargs)
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]

        out = []
        for rank, (doc, meta, dist) in enumerate(zip(docs, metas, dists, strict=True)):
            out.append(Passage(
                chunk_id=self._meta_id(meta),
                text=doc,
                filename=str(meta.get("filename", "unknown")),
                jurisdiction=str(meta.get("jurisdiction", "unknown")),
                page_number=int(meta.get("page_number", 0)),
                chunk_index=int(meta.get("chunk_index", 0)),
                distance=float(dist),
                dense_rank=rank,
            ))
        return out

    @staticmethod
    def _meta_id(meta: dict) -> str:
        fn = str(meta.get("filename", "unknown")).replace(" ", "_")
        return f"{fn}::p{int(meta.get('page_number', 0))}::c{int(meta.get('chunk_index', 0))}"

    # -- lexical ----------------------------------------------------------

    def _lexical_ids(self, query: str, jurisdictions: list[str], k: int) -> list[str]:
        self._ensure_bm25()
        if self._bm25 is None:
            return []
        tokens = tokenize(query, split_compounds=True)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        allowed = set(jurisdictions) if jurisdictions else None

        order = np.argsort(scores)[::-1]
        picked: list[str] = []
        for idx in order:
            if scores[idx] <= 0:
                break
            if allowed is not None and self._bm25_jx[idx] not in allowed:
                continue
            picked.append(self._bm25_ids[idx])
            if len(picked) >= k:
                break
        return picked

    def _hydrate(self, chunk_ids: Iterable[str], query: str) -> list[Passage]:
        """
        Turn lexical-only hits into Passages with a real cosine distance, by
        fetching their stored embeddings and scoring them against the query.
        """
        ids = list(chunk_ids)
        if not ids or self._ef is None:
            return []
        try:
            got = self._collection.get(
                ids=ids, include=["documents", "metadatas", "embeddings"]
            )
            q_vec = np.asarray(
                self._ef([query])[0], dtype=float
            )
            q_norm = np.linalg.norm(q_vec) or 1.0
        except Exception as exc:
            logger.warning("Could not hydrate lexical hits: %s", exc)
            return []

        out = []
        # Chroma returns embeddings as a numpy array -- test for None, not truth.
        embeddings = got.get("embeddings")
        if embeddings is None:
            embeddings = []
        ids_back = got.get("ids") or []
        for i, cid in enumerate(ids_back):
            meta = got["metadatas"][i]
            try:
                vec = np.asarray(embeddings[i], dtype=float)
                cos = float(vec @ q_vec / ((np.linalg.norm(vec) or 1.0) * q_norm))
                distance = 1.0 - cos
            except (IndexError, ValueError, TypeError):
                distance = 1.0
            out.append(Passage(
                chunk_id=cid,
                text=got["documents"][i],
                filename=str(meta.get("filename", "unknown")),
                jurisdiction=str(meta.get("jurisdiction", "unknown")),
                page_number=int(meta.get("page_number", 0)),
                chunk_index=int(meta.get("chunk_index", 0)),
                distance=distance,
            ))
        return out

    # -- public -----------------------------------------------------------

    def search(
        self,
        query: str,
        jurisdictions: list[str] | None = None,
        *,
        top_k: int | None = None,
        balance: bool | None = None,
    ) -> RetrievalResult:
        """
        Retrieve the most relevant passages for `query`.

        jurisdictions: Chroma jurisdiction values to restrict to; empty/None
                       searches everything.
        balance:       cap passages per jurisdiction. Defaults to on when
                       searching more than one jurisdiction, so that the
                       largest corpus (EU, ~47% of chunks) cannot crowd out the
                       rest of a cross-jurisdiction answer.
        """
        jurisdictions = list(jurisdictions or [])
        top_k = top_k or config.TOP_K
        if balance is None:
            balance = len(jurisdictions) != 1
        # Expansion feeds BM25 only. Appending words to the dense query moves
        # its embedding, and with it every distance the relevance gate is tuned on.
        lex_query = expand_query(query) if config.QUERY_EXPANSION else query

        dense = self._dense(query, jurisdictions, config.CANDIDATE_K)
        by_id: dict[str, Passage] = {p.chunk_id: p for p in dense}

        if self._hybrid:
            lex_ids = self._lexical_ids(lex_query, jurisdictions, config.CANDIDATE_K)
            missing = [cid for cid in lex_ids if cid not in by_id]
            for p in self._hydrate(missing, query):
                by_id[p.chunk_id] = p
            for rank, cid in enumerate(lex_ids):
                if cid in by_id:
                    by_id[cid].lexical_rank = rank

        # Reciprocal Rank Fusion: robust to the two retrievers' scores being
        # on completely different scales.
        k = config.RRF_K
        for p in by_id.values():
            score = 0.0
            if p.dense_rank is not None:
                score += 1.0 / (k + p.dense_rank + 1)
            if p.lexical_rank is not None:
                score += 1.0 / (k + p.lexical_rank + 1)
            p.fused_score = score

        candidates = sorted(
            by_id.values(), key=lambda p: (-p.fused_score, p.distance)
        )
        best = min((p.distance for p in candidates), default=None)

        relevant = [p for p in candidates if p.distance <= config.MAX_DISTANCE]
        if not relevant:
            return RetrievalResult([], quality="no_match", best_distance=best)

        selected = self._balance(relevant, top_k) if balance else relevant[:top_k]
        quality = "weak" if best is not None and best > config.WEAK_DISTANCE else "ok"
        return RetrievalResult(selected, quality=quality, best_distance=best)

    def _balance(self, passages: list[Passage], top_k: int) -> list[Passage]:
        """
        Take the best passages while capping how many any one jurisdiction may
        contribute, then backfill from the remainder if that leaves us short.

        The cap is deliberately SOFT. Its job is to guarantee that a dominant
        corpus (EU is ~47% of the chunks) cannot shut smaller jurisdictions out
        of a cross-jurisdiction answer -- not to leave context slots empty. When
        a question genuinely only has EU material, five EU passages beat two EU
        passages plus three wasted slots, so the backfill is allowed past the
        cap once every jurisdiction has had its turn.
        """
        cap = max(1, config.MAX_PER_JURISDICTION)
        picked: list[Passage] = []
        counts: dict[str, int] = {}
        overflow: list[Passage] = []

        for p in passages:
            if len(picked) >= top_k:
                break
            group = self._group_of.get(p.jurisdiction, p.jurisdiction)
            n = counts.get(group, 0)
            if n < cap:
                picked.append(p)
                counts[group] = n + 1
            else:
                overflow.append(p)

        for p in overflow:
            if len(picked) >= top_k:
                break
            picked.append(p)

        return picked
