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

CREATE TABLE IF NOT EXISTS journals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    publisher           TEXT NOT NULL,
    toc_url             TEXT UNIQUE NOT NULL,
    issn                TEXT,
    last_checked        TEXT,
    current_issue_label TEXT,
    has_new_issue       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS toc_articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id   INTEGER NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
    url          TEXT NOT NULL,
    doi          TEXT,
    title        TEXT NOT NULL,
    authors      TEXT,
    article_type TEXT,
    abstract     TEXT,
    issue_label  TEXT,
    UNIQUE(journal_id, url)
);

CREATE TABLE IF NOT EXISTS reading_list (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    toc_article_id INTEGER NOT NULL REFERENCES toc_articles(id) ON DELETE CASCADE,
    article_id     INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    added_at       TEXT NOT NULL,
    UNIQUE(toc_article_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
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


# ── Journal operations ────────────────────────────────────────────────────────

def add_journal(name: str, publisher: str, toc_url: str, issn: str | None = None) -> int:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO journals (name, publisher, toc_url, issn) VALUES (?,?,?,?)",
            (name, publisher, toc_url, issn),
        )
        row = conn.execute("SELECT id FROM journals WHERE toc_url = ?", (toc_url,)).fetchone()
        return row["id"]


def remove_journal(journal_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM journals WHERE id = ?", (journal_id,))


def get_journals() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM journals ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_journal(journal_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM journals WHERE id = ?", (journal_id,)).fetchone()
    return dict(row) if row else None


def get_journal_by_url(toc_url: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM journals WHERE toc_url = ?", (toc_url,)).fetchone()
    return dict(row) if row else None


def update_journal_toc(
    journal_id: int,
    issue_label: str,
    articles: list[dict],
    is_new: bool,
) -> None:
    """
    Replace the TOC for a journal. Each dict in articles must have:
      url, title, and optionally: doi, authors (list), article_type, abstract, issue_label
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE journals SET last_checked=?, current_issue_label=?, has_new_issue=? WHERE id=?",
            (now, issue_label, 1 if is_new else 0, journal_id),
        )
        for a in articles:
            conn.execute("""
                INSERT INTO toc_articles (journal_id, url, doi, title, authors, article_type, abstract, issue_label)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(journal_id, url) DO UPDATE SET
                    doi=excluded.doi, title=excluded.title, authors=excluded.authors,
                    article_type=excluded.article_type, abstract=excluded.abstract,
                    issue_label=excluded.issue_label
            """, (
                journal_id,
                a["url"],
                a.get("doi"),
                a["title"],
                json.dumps(a.get("authors", [])),
                a.get("article_type"),
                a.get("abstract"),
                a.get("issue_label", issue_label),
            ))


def get_toc_articles(journal_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM toc_articles WHERE journal_id = ? ORDER BY id",
            (journal_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["authors"] = json.loads(d["authors"] or "[]")
        except (json.JSONDecodeError, TypeError):
            d["authors"] = []
        result.append(d)
    return result


# ── Reading list operations ───────────────────────────────────────────────────

def add_to_reading_list(toc_article_id: int) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO reading_list (toc_article_id, added_at) VALUES (?,?)",
            (toc_article_id, now),
        )
        row = conn.execute(
            "SELECT id FROM reading_list WHERE toc_article_id = ?", (toc_article_id,)
        ).fetchone()
        return row["id"]


def remove_from_reading_list(toc_article_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM reading_list WHERE toc_article_id = ?", (toc_article_id,))


def link_reading_list_to_article(toc_article_id: int, article_id: int) -> None:
    """Call this after a TOC article's PDF download completes."""
    with _connect() as conn:
        conn.execute(
            "UPDATE reading_list SET article_id = ? WHERE toc_article_id = ?",
            (article_id, toc_article_id),
        )


def get_reading_list() -> list[dict]:
    """
    Returns reading list entries joined with toc_article and journal info,
    and optionally the article pdf_path if downloaded.
    """
    with _connect() as conn:
        rows = conn.execute("""
            SELECT rl.id, rl.toc_article_id, rl.article_id, rl.added_at,
                   ta.title, ta.authors, ta.url, ta.doi, ta.article_type, ta.issue_label,
                   j.name AS journal_name,
                   a.pdf_path
            FROM reading_list rl
            JOIN toc_articles ta ON ta.id = rl.toc_article_id
            JOIN journals j ON j.id = ta.journal_id
            LEFT JOIN articles a ON a.id = rl.article_id
            ORDER BY rl.added_at DESC
        """).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["authors"] = json.loads(d["authors"] or "[]")
        except (json.JSONDecodeError, TypeError):
            d["authors"] = []
        result.append(d)
    return result


def get_reading_list_ids() -> set[int]:
    """Return the set of toc_article_ids currently in the reading list."""
    with _connect() as conn:
        rows = conn.execute("SELECT toc_article_id FROM reading_list").fetchall()
    return {r["toc_article_id"] for r in rows}


# ── Settings operations ───────────────────────────────────────────────────────

_SETTINGS_KEYS = [
    "huji_email", "huji_password",
    "resend_api_key", "resend_from",
    "email_to_1", "email_to_2", "email_to_3",
]


def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_all_settings() -> dict[str, str]:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}
