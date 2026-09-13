"""
Healdar analytics — lightweight SQLite usage tracking.

One row per query. Question text is NOT stored by default: questions can carry
commercially sensitive or personal detail, and the aggregate counts this panel
shows do not need it. Set HEALDAR_ANALYTICS_QUESTIONS=1 to opt in.

All timestamps are UTC, and "today" is evaluated in UTC too, so the daily count
cannot disagree with the rows it is counting.

Note on hosting: on an ephemeral filesystem (HuggingFace Spaces, Streamlit
Cloud) this database is wiped on every restart. It measures a deployment, not
a lifetime.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import config

DB_PATH: Path = config.RUNTIME_DIR / "analytics.db"

_DDL = """
CREATE TABLE IF NOT EXISTS queries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,   -- ISO-8601, UTC
    question     TEXT,               -- NULL unless opted in
    language     TEXT    NOT NULL,   -- 'en' | 'ar'
    mode         TEXT    NOT NULL,   -- 'single' | 'compare'
    jurisdiction TEXT,               -- single mode
    jx_left      TEXT,               -- compare mode
    jx_right     TEXT,               -- compare mode
    response_ms  INTEGER,            -- wall-clock ms for the query
    no_context   INTEGER DEFAULT 0   -- 1 if nothing relevant was found
);
CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp);
"""

_COLUMNS = [
    "id", "timestamp", "question", "language", "mode",
    "jurisdiction", "jx_left", "jx_right", "response_ms", "no_context",
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _utc_today() -> str:
    return datetime.now(UTC).date().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")   # safe across concurrent sessions
    return conn


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the database and table if they do not exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_DDL)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def log_query(
    question:     str,
    language:     str,
    mode:         str,
    jurisdiction: str | None = None,
    jx_left:      str | None = None,
    jx_right:     str | None = None,
    response_ms:  int | None = None,
    no_context:   bool = False,
) -> None:
    """Record one query. Never raises — analytics must not break the app."""
    try:
        stored_question = question if config.ANALYTICS_STORE_QUESTIONS else None
        with _connect() as conn:
            conn.execute(
                """INSERT INTO queries
                   (timestamp, question, language, mode, jurisdiction,
                    jx_left, jx_right, response_ms, no_context)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    _utc_now(), stored_question, language, mode, jurisdiction,
                    jx_left, jx_right, response_ms, int(no_context),
                ),
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Read — summary stats
# ---------------------------------------------------------------------------

def get_summary() -> dict:
    """Aggregated stats as a plain dict. Safe to call when the DB is missing."""
    try:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row

            total = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
            if not total:
                return {"total": 0}

            today = conn.execute(
                "SELECT COUNT(*) FROM queries WHERE timestamp LIKE ?",
                (f"{_utc_today()}%",),
            ).fetchone()[0]

            lang_rows = conn.execute(
                "SELECT language, COUNT(*) n FROM queries "
                "GROUP BY language ORDER BY n DESC"
            ).fetchall()

            jx_rows = conn.execute(
                "SELECT jurisdiction, COUNT(*) n FROM queries "
                "WHERE jurisdiction IS NOT NULL AND mode='single' "
                "GROUP BY jurisdiction ORDER BY n DESC LIMIT 5"
            ).fetchall()

            compare_n = conn.execute(
                "SELECT COUNT(*) FROM queries WHERE mode='compare'"
            ).fetchone()[0]

            avg_ms = conn.execute(
                "SELECT AVG(response_ms) FROM queries WHERE response_ms IS NOT NULL"
            ).fetchone()[0]

            no_ctx_n = conn.execute(
                "SELECT COUNT(*) FROM queries WHERE no_context=1"
            ).fetchone()[0]

            return {
                "total":             total,
                "today":             today,
                "languages":         [dict(r) for r in lang_rows],
                "top_jurisdictions": [dict(r) for r in jx_rows],
                "compare_pct":       round(compare_n / total * 100),
                "avg_response_ms":   round(avg_ms) if avg_ms else None,
                "no_context_pct":    round(no_ctx_n / total * 100),
            }
    except Exception:
        return {"total": 0}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_csv() -> bytes:
    """All rows as UTF-8 CSV bytes. Returns a header-only file on failure."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_COLUMNS)
    writer.writeheader()
    try:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM queries ORDER BY timestamp DESC"
            ).fetchall()
        writer.writerows([{k: r[k] for k in _COLUMNS} for r in rows])
    except Exception:
        pass
    return buf.getvalue().encode("utf-8")
