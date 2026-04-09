# journal_club/storage.py
"""
SQLite persistence layer for Journal Club.
DB file: journal_club.db in the project root (next to download.py).
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from journal_club.resolver import ArticleMetadata

_DB_PATH = Path(__file__).parent.parent / "journal_club.db"


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT UNIQUE NOT NULL,
    pmid          TEXT,
    doi           TEXT,
    title         TEXT,
    authors       TEXT,          -- JSON array
    journal       TEXT,
    pub_date      TEXT,
    abstract      TEXT,
    pdf_path      TEXT,          -- NULL until download succeeds
    downloaded_at TEXT,          -- ISO-8601
    is_bookmarked INTEGER NOT NULL DEFAULT 0
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(_DDL)
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["authors"] = json.loads(d["authors"] or "[]")
    except (json.JSONDecodeError, TypeError):
        d["authors"] = []
    d["is_bookmarked"] = bool(d["is_bookmarked"])
    return d


# ── Write operations ──────────────────────────────────────────────────────────

def save_article(meta: ArticleMetadata, pdf_path: str | None = None) -> int:
    """
    Insert or update an article record.
    If a record with the same URL already exists, update metadata and pdf_path.
    Returns the row id.
    """
    now = datetime.now(timezone.utc).isoformat()
    authors_json = json.dumps(meta.authors)
    with _connect() as conn:
        conn.execute("""
            INSERT INTO articles
                (url, pmid, doi, title, authors, journal, pub_date, abstract,
                 pdf_path, downloaded_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET
                pmid          = excluded.pmid,
                doi           = excluded.doi,
                title         = excluded.title,
                authors       = excluded.authors,
                journal       = excluded.journal,
                pub_date      = excluded.pub_date,
                abstract      = excluded.abstract,
                pdf_path      = COALESCE(excluded.pdf_path, articles.pdf_path),
                downloaded_at = excluded.downloaded_at
        """, (meta.url, meta.pmid, meta.doi, meta.title, authors_json,
              meta.journal, meta.pub_date, meta.abstract, pdf_path, now))
        row = conn.execute("SELECT id FROM articles WHERE url = ?", (meta.url,)).fetchone()
        return row["id"]


def update_pdf_path(article_id: int, pdf_path: str) -> None:
    """Set pdf_path after a background download completes."""
    with _connect() as conn:
        conn.execute(
            "UPDATE articles SET pdf_path = ?, downloaded_at = ? WHERE id = ?",
            (pdf_path, datetime.now(timezone.utc).isoformat(), article_id),
        )


def toggle_bookmark(article_id: int) -> bool:
    """Flip is_bookmarked. Returns the new state."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT is_bookmarked FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        if row is None:
            return False
        new_val = 0 if row["is_bookmarked"] else 1
        conn.execute(
            "UPDATE articles SET is_bookmarked = ? WHERE id = ?", (new_val, article_id)
        )
        return bool(new_val)


# ── Read operations ───────────────────────────────────────────────────────────

def get_history() -> list[dict]:
    """All articles, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM articles ORDER BY downloaded_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_bookmarks() -> list[dict]:
    """Bookmarked articles only, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE is_bookmarked = 1 ORDER BY downloaded_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(article_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_url(url: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM articles WHERE url = ?", (url,)
        ).fetchone()
    return _row_to_dict(row) if row else None
