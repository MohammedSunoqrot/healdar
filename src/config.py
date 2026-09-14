"""
Healdar — central configuration.

Everything tunable lives here and can be overridden with an environment
variable, so a deployment can change models or thresholds without a code
change. Import this rather than re-declaring constants in each module.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Release -- shown in the sidebar so users can tell which build answered them.
# ---------------------------------------------------------------------------
APP_VERSION  = "2.1.1"
RELEASE_DATE = "2026-09-14"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SRC_DIR      = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"
CHUNKS_FILE  = DATA_DIR / "processed" / "chunks.json"
VECTORSTORE  = DATA_DIR / "processed" / "vectorstore"
RAW_DOCS_DIR = DATA_DIR / "raw_docs"
RUNTIME_DIR  = DATA_DIR / "runtime"
ENV_FILE     = PROJECT_ROOT / ".env"


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Vector store / embeddings
# ---------------------------------------------------------------------------
COLLECTION_NAME = _env_str("HEALDAR_COLLECTION", "regradar")
# Multilingual: the UAE PDPL is indexed in its official Arabic, and this model
# retrieves it from English questions. Chosen by benchmark on this corpus
# (hit@5, plus a clean gap between on- and off-topic distances so the
# relevance gate can refuse):
#   all-MiniLM-L6-v2 (English only)         89.8%  gap +0.255  misses the Arabic law
#   intfloat/multilingual-e5-small          87.0%  gap -0.011  cannot gate at all
#   paraphrase-multilingual-MiniLM-L12-v2   92.6%  gap +0.261
# Changing it requires `python src/embed.py --rebuild` and re-measuring the gate.
EMBED_MODEL     = _env_str(
    "HEALDAR_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# Auto-rebuild the Chroma index from chunks.json when it is missing or
# unreadable (corrupt index, un-pulled Git LFS pointer, Chroma version bump).
AUTO_REBUILD_VECTORSTORE = _env_bool("HEALDAR_AUTO_REBUILD", True)

# ---------------------------------------------------------------------------
# Groq models
#
# llama-3.1-8b-instant and llama-3.3-70b-versatile were DECOMMISSIONED on
# 2026-08-16 for free and developer tiers. Requests to them now return errors.
# See https://console.groq.com/docs/deprecations before changing these.
#
#   SMALL  — cheap, high-throughput: query translation, follow-up rewriting
#   LARGE  — high quality: Arabic translation of the final answer
#   ANSWER — the model that actually writes the regulatory answer
# ---------------------------------------------------------------------------
GROQ_MODEL_SMALL  = _env_str("GROQ_MODEL",        "openai/gpt-oss-20b")
GROQ_MODEL_LARGE  = _env_str("GROQ_MODEL_LARGE",  "openai/gpt-oss-120b")
GROQ_MODEL_ANSWER = _env_str("GROQ_MODEL_ANSWER", GROQ_MODEL_LARGE)

GROQ_TIMEOUT     = _env_float("GROQ_TIMEOUT", 45.0)
GROQ_MAX_RETRIES = _env_int("GROQ_MAX_RETRIES", 2)

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
TOP_K       = _env_int("HEALDAR_TOP_K", 5)          # passages handed to the LLM
CANDIDATE_K = _env_int("HEALDAR_CANDIDATE_K", 20)   # pool fetched before fusion

# Chroma returns cosine DISTANCE (0 = identical, 2 = opposite).
# Measured on this corpus with paraphrase-multilingual-MiniLM-L12-v2, best
# match per question over the golden set:
#   on-topic regulatory questions  ->  at most  0.403  (mean 0.228)
#   clearly off-topic questions    ->  at least 0.664  (mean 0.726)
# 0.53 sits mid-way in the empty band between the two. Re-measure whenever
# the embedding model or the corpus changes.
MAX_DISTANCE = _env_float("HEALDAR_MAX_DISTANCE", 0.53)

# Above this, material was found but is a weak match — answer, but warn.
WEAK_DISTANCE = _env_float("HEALDAR_WEAK_DISTANCE", 0.45)

# Lexical (BM25) search alongside dense search. Regulatory questions lean on
# exact tokens ("Article 120", "MDS-G010", "Annex VIII") that embeddings blur.
HYBRID_SEARCH  = _env_bool("HEALDAR_HYBRID", True)
RRF_K          = _env_int("HEALDAR_RRF_K", 60)   # reciprocal-rank-fusion constant
# Append spelled-out forms of acronyms (AI, SaMD, PDPL, ...) to the query; see
# retrieval.expand_query for the measurement behind it.
QUERY_EXPANSION = _env_bool("HEALDAR_QUERY_EXPANSION", True)
# Before searching, a small model names the provisions and guidance a question
# depends on ("MDR Annex VIII Rule 11 software classification"), and each is
# searched alongside the question itself. Case-style questions ("suggest the
# class of this retinal-screening software") otherwise land on FAQ pages rather
# than the rule that decides them. The user's own question still decides refusal.
QUERY_PLANNING  = _env_bool("HEALDAR_QUERY_PLANNING", True)
PLANNED_QUERIES = _env_int("HEALDAR_PLANNED_QUERIES", 3)
# The 120b model, ~1 s on Groq: the 20b one guessed wrong provisions, looped,
# or spent its whole budget reasoning and returned nothing.
GROQ_MODEL_PLANNER = _env_str("GROQ_MODEL_PLANNER", GROQ_MODEL_LARGE)
# How many of the question's own top passages always survive fusion. Planned
# retrieval returns TOP_K + this many, so planned evidence gets its own slots.
PLAN_KEEP_ORIGINAL = _env_int("HEALDAR_PLAN_KEEP_ORIGINAL", 2)

# In "all jurisdictions" mode, cap how many passages one jurisdiction may take.
# EU is ~47% of the corpus, so an unbalanced top-5 is usually 4x EU.
MAX_PER_JURISDICTION = _env_int("HEALDAR_MAX_PER_JX", 2)

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
ANSWER_MAX_TOKENS    = _env_int("HEALDAR_ANSWER_MAX_TOKENS", 1400)
ANSWER_TEMPERATURE   = _env_float("HEALDAR_ANSWER_TEMPERATURE", 0.2)
HISTORY_TURNS        = _env_int("HEALDAR_HISTORY_TURNS", 3)
# How much of the latest answer a follow-up sees -- its opening and its end,
# where the conclusion is -- enough to argue with its reasoning ("why IIb and
# not IIa?"). Older turns get 400 characters.
HISTORY_ANSWER_CHARS = _env_int("HEALDAR_HISTORY_ANSWER_CHARS", 2400)
# Pages the previous answer cited that a follow-up starts from.
CARRY_SOURCES        = _env_int("HEALDAR_CARRY_SOURCES", 3)

# ---------------------------------------------------------------------------
# App behaviour
# ---------------------------------------------------------------------------
DEV_MODE = _env_bool("HEALDAR_DEV", False)

# Persist chat history to disk. OFF by default: the file is process-wide, so on
# a shared deployment one visitor would load another visitor's history.
PERSIST_SESSION = _env_bool("HEALDAR_PERSIST_SESSION", False)

# Store the raw question text in the analytics DB. OFF by default — questions
# can contain personal or commercially sensitive information.
ANALYTICS_STORE_QUESTIONS = _env_bool("HEALDAR_ANALYTICS_QUESTIONS", False)

# Per-session throttle so a public deployment cannot drain the API quota.
RATE_LIMIT_QUERIES = _env_int("HEALDAR_RATE_LIMIT_QUERIES", 0)   # 0 = disabled
RATE_LIMIT_WINDOW  = _env_int("HEALDAR_RATE_LIMIT_WINDOW", 600)  # seconds

# ---------------------------------------------------------------------------
# Shared patterns
#
# One definition used by the pipeline, the UI and both exporters. Matches the
# clean tag "[Source 3]" and the legacy verbose "[Source 3: file.pdf | p.4]".
# ---------------------------------------------------------------------------
# Models do not always use ASCII brackets: gpt-oss regularly writes
# 【Source 2】 (U+3010/U+3011) and occasionally the full-width ［Source 2］.
# Those were neither rendered as footnotes nor matched to references, so the
# answer silently lost its reference list. rag_pipeline rewrites every variant
# to the canonical "[Source N]" right after generation; accepting them here as
# well keeps anything stored before that change readable.
CITATION_RE = re.compile(
    r"[\[【［]\s*Source\s*(\d+)[^\]】］]*[\]】］]", re.IGNORECASE
)
