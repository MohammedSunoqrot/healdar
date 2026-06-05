"""
Healdar Analytics — lightweight SQLite-backed usage tracking.

Schema: one row per query. No PII beyond the question text.
DB lives at data/analytics.db (excluded from Docker image if desired).
"""

import csv
import io
import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "runtime" / "analytics.db"

_DDL = """
CREATE TABLE IF NOT EXISTS queries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,
    question     TEXT    NOT NULL,
    language     TEXT    NOT NULL,   -- 'en' | 'ar'
    mode         TEXT    NOT NULL,   -- 'single' | 'compare'
    jurisdiction TEXT,               -- single mode
    jx_left      TEXT,               -- compare mode
    jx_right     TEXT,               -- compare mode
    response_ms  INTEGER,            -- wall-clock ms for rag.ask()
    no_context   INTEGER DEFAULT 0   -- 1 if no relevant docs found
);
"""


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the database and table if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # safe for concurrent Streamlit sessions
        conn.execute(_DDL)


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
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO queries
                   (timestamp, question, language, mode, jurisdiction,
                    jx_left, jx_right, response_ms, no_context)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    datetime.utcnow().isoformat(timespec="seconds"),
                    question,
                    language,
                    mode,
                    jurisdiction,
                    jx_left,
                    jx_right,
                    response_ms,
                    int(no_context),
                ),
            )
    except Exception:
        pass  # analytics must never crash the main app


# ---------------------------------------------------------------------------
# Read — summary stats
# ---------------------------------------------------------------------------

def get_summary() -> dict:
    """Return aggregated stats as a plain dict. Safe to call if DB missing."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            total = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
            if total == 0:
                return {"total": 0}

            today = conn.execute(
                "SELECT COUNT(*) FROM queries WHERE timestamp LIKE ?",
                (f"{date.today().isoformat()}%",),
            ).fetchone()[0]

            lang_rows = conn.execute(
                "SELECT language, COUNT(*) n FROM queries GROUP BY language ORDER BY n DESC"
            ).fetchall()

            jx_rows = conn.execute(
                """SELECT jurisdiction, COUNT(*) n FROM queries
                   WHERE jurisdiction IS NOT NULL AND mode='single'
                   GROUP BY jurisdiction ORDER BY n DESC LIMIT 5"""
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
                "total":            total,
                "today":            today,
                "languages":        [dict(r) for r in lang_rows],
                "top_jurisdictions": [dict(r) for r in jx_rows],
                "compare_pct":      round(compare_n / total * 100) if total else 0,
                "avg_response_ms":  round(avg_ms) if avg_ms else None,
                "no_context_pct":   round(no_ctx_n / total * 100) if total else 0,
            }
    except Exception:
        return {"total": 0}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_csv() -> bytes:
    """Return all rows as UTF-8 CSV bytes."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM queries ORDER BY timestamp DESC"
            ).fetchall()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "id", "timestamp", "question", "language", "mode",
            "jurisdiction", "jx_left", "jx_right", "response_ms", "no_context",
        ])
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])
        return buf.getvalue().encode("utf-8")
    except Exception:
        return b"id,timestamp,question,language,mode,jurisdiction,jx_left,jx_right,response_ms,no_context\n"
