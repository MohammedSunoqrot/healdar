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
EMBED_MODEL     = _env_str("HEALDAR_EMBED_MODEL", "all-MiniLM-L6-v2")

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
# Measured on this corpus with all-MiniLM-L6-v2:
#   on-topic regulatory queries  ->  0.185 .. 0.475
#   clearly off-topic queries    ->  0.759 .. 0.912
# 0.62 sits in the empty band between the two, with margin on both sides.
MAX_DISTANCE = _env_float("HEALDAR_MAX_DISTANCE", 0.62)

# Above this, material was found but is a weak match — answer, but warn.
WEAK_DISTANCE = _env_float("HEALDAR_WEAK_DISTANCE", 0.52)

# Lexical (BM25) search alongside dense search. Regulatory questions lean on
# exact tokens ("Article 120", "MDS-G010", "Annex VIII") that embeddings blur.
HYBRID_SEARCH  = _env_bool("HEALDAR_HYBRID", True)
RRF_K          = _env_int("HEALDAR_RRF_K", 60)   # reciprocal-rank-fusion constant

# In "all jurisdictions" mode, cap how many passages one jurisdiction may take.
# EU is ~47% of the corpus, so an unbalanced top-5 is usually 4x EU.
MAX_PER_JURISDICTION = _env_int("HEALDAR_MAX_PER_JX", 2)

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
ANSWER_MAX_TOKENS    = _env_int("HEALDAR_ANSWER_MAX_TOKENS", 1400)
ANSWER_TEMPERATURE   = _env_float("HEALDAR_ANSWER_TEMPERATURE", 0.2)
HISTORY_TURNS        = _env_int("HEALDAR_HISTORY_TURNS", 3)

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
CITATION_RE = re.compile(r"\[Source\s*(\d+)[^\]]*\]", re.IGNORECASE)
