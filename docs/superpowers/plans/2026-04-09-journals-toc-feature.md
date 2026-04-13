# Journals TOC Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Journals page where users follow medical journals, see the current issue TOC in a two-panel layout, download PDFs directly, add articles to a Reading List, and email the Reading List PDFs on demand.

**Architecture:** A curated catalog of ~15 major journals (+ free-form URL fallback) is stored in SQLite. A weekly APScheduler background job scrapes each followed journal's TOC page using requests + BeautifulSoup and stores results in `toc_articles`. Reading list is a lightweight join table; emailing uses Python's stdlib smtplib with PDF attachments.

**Tech Stack:** Flask, SQLite (WAL), APScheduler, requests, BeautifulSoup4, smtplib, Tailwind CSS (already in use)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `journal_club/journals_catalog.py` | Static list of ~15 curated journals (name, publisher, toc_url, issn) |
| Create | `journal_club/toc_scraper.py` | HTTP + BS4 TOC scrapers, one function per publisher family |
| Create | `journal_club/mailer.py` | Build and send reading-list email via smtplib |
| Create | `templates/journals.html` | Two-panel journals page (journal list left, TOC right) |
| Modify | `journal_club/storage.py` | Add journals/toc_articles/reading_list tables + CRUD functions |
| Modify | `journal_club/config.py` | Add email_to, smtp_host, smtp_port, smtp_user, smtp_password |
| Modify | `app.py` | Add /journals routes + APScheduler weekly refresh |
| Modify | `templates/base.html` | Add Journals nav item |
| Modify | `config.yaml` | Add email fields |

---

## Task 1: DB Schema — journals, toc_articles, reading_list

**Files:**
- Modify: `journal_club/storage.py`

The three new tables extend the existing `_DDL` string and add new CRUD functions.

- [ ] **Step 1: Add DDL for new tables to `_DDL` in `journal_club/storage.py`**

Replace the existing `_DDL` constant (currently a single `CREATE TABLE IF NOT EXISTS articles` block) with:

```python
_DDL = """
CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT UNIQUE NOT NULL,
    pmid          TEXT,
    doi           TEXT,
    title         TEXT,
    authors       TEXT,
    journal       TEXT,
    pub_date      TEXT,
    abstract      TEXT,
    pdf_path      TEXT,
    downloaded_at TEXT,
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
"""
```

- [ ] **Step 2: Add journal CRUD functions after the existing `get_by_url` function**

```python
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
```

- [ ] **Step 3: Verify DB initialises cleanly**

```bash
cd "C:\Users\ysomp\OneDrive\Documents\Journal Club"
python -c "import journal_club.storage as s; s._connect(); print('OK')"
```

Expected: `OK` with no errors.

- [ ] **Step 4: Commit**

```bash
git add journal_club/storage.py
git commit -m "feat: add journals/toc_articles/reading_list DB schema and storage functions"
```

---

## Task 2: Journal Catalog

**Files:**
- Create: `journal_club/journals_catalog.py`

A static list of major medical journals. This is the data that populates the "Add journal" catalog.

- [ ] **Step 1: Create `journal_club/journals_catalog.py`**

```python
# journal_club/journals_catalog.py
"""
Static catalog of major medical journals.
Each entry: name, publisher, toc_url, issn
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    publisher: str      # Used by toc_scraper to pick the right parser
    toc_url: str
    issn: str | None = None


CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        name="New England Journal of Medicine",
        publisher="nejm",
        toc_url="https://www.nejm.org/toc/nejm/current",
        issn="0028-4793",
    ),
    CatalogEntry(
        name="JAMA",
        publisher="jama",
        toc_url="https://jamanetwork.com/journals/jama/issue/current",
        issn="0098-7484",
    ),
    CatalogEntry(
        name="The Lancet",
        publisher="lancet",
        toc_url="https://www.thelancet.com/journals/lancet/issue/current",
        issn="0140-6736",
    ),
    CatalogEntry(
        name="Nature Medicine",
        publisher="nature",
        toc_url="https://www.nature.com/nm/current-issue",
        issn="1078-8956",
    ),
    CatalogEntry(
        name="BMJ",
        publisher="bmj",
        toc_url="https://www.bmj.com/content/current",
        issn="0959-8138",
    ),
    CatalogEntry(
        name="Annals of Internal Medicine",
        publisher="acpjournals",
        toc_url="https://www.acpjournals.org/toc/aim/current",
        issn="0003-4819",
    ),
    CatalogEntry(
        name="Circulation",
        publisher="ahajournals",
        toc_url="https://www.ahajournals.org/toc/circ/current",
        issn="0009-7322",
    ),
    CatalogEntry(
        name="JACC",
        publisher="jacc",
        toc_url="https://www.jacc.org/toc/jacc/current",
        issn="0735-1097",
    ),
    CatalogEntry(
        name="CHEST",
        publisher="chest",
        toc_url="https://journal.chestnet.org/current",
        issn="0012-3692",
    ),
    CatalogEntry(
        name="Journal of Clinical Oncology",
        publisher="asco",
        toc_url="https://ascopubs.org/toc/jco/current",
        issn="0732-183X",
    ),
    CatalogEntry(
        name="Gut",
        publisher="bmj",
        toc_url="https://gut.bmj.com/content/current",
        issn="0017-5749",
    ),
    CatalogEntry(
        name="Blood",
        publisher="blood",
        toc_url="https://ashpublications.org/blood/issue",
        issn="0006-4971",
    ),
    CatalogEntry(
        name="Diabetes Care",
        publisher="diabetesjournals",
        toc_url="https://diabetesjournals.org/care/issue/current",
        issn="0149-5992",
    ),
    CatalogEntry(
        name="NEJM Evidence",
        publisher="nejm",
        toc_url="https://evidence.nejm.org/toc/evid/current",
        issn="2766-5526",
    ),
    CatalogEntry(
        name="JAMA Internal Medicine",
        publisher="jama",
        toc_url="https://jamanetwork.com/journals/jamainternalmedicine/issue/current",
        issn="2168-6106",
    ),
]
```

- [ ] **Step 2: Verify import**

```bash
python -c "from journal_club.journals_catalog import CATALOG; print(len(CATALOG), 'journals')"
```

Expected: `15 journals`

- [ ] **Step 3: Commit**

```bash
git add journal_club/journals_catalog.py
git commit -m "feat: add curated journal catalog with 15 major medical journals"
```

---

## Task 3: TOC Scraper

**Files:**
- Create: `journal_club/toc_scraper.py`

Fetches and parses a journal's current-issue TOC page. Returns a `TocResult` with the issue label and list of article dicts. Each publisher has its own `_parse_*` function.

**Dependency:** `pip install beautifulsoup4` (requests is already installed).

- [ ] **Step 1: Install beautifulsoup4**

```bash
pip install beautifulsoup4
```

Expected: `Successfully installed beautifulsoup4-...`

- [ ] **Step 2: Create `journal_club/toc_scraper.py`**

```python
# journal_club/toc_scraper.py
"""
Scrape the current-issue table of contents for a followed journal.

Usage:
    from journal_club.toc_scraper import scrape
    result = scrape(publisher="nejm", toc_url="https://www.nejm.org/toc/nejm/current")
    print(result.issue_label, len(result.articles))
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 20


@dataclass
class TocResult:
    issue_label: str                          # e.g. "Vol 392 · Issue 19 · May 2025"
    articles: list[dict] = field(default_factory=list)
    # Each article dict has keys: url, title, authors (list), article_type, doi, abstract


def scrape(publisher: str, toc_url: str) -> TocResult:
    """
    Fetch and parse a journal's current-issue TOC.
    publisher must match one of the CatalogEntry.publisher values.
    Raises requests.HTTPError on non-200 responses.
    """
    r = requests.get(toc_url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    parsers = {
        "nejm":           _parse_nejm,
        "jama":           _parse_jama,
        "lancet":         _parse_lancet,
        "nature":         _parse_nature,
        "bmj":            _parse_bmj,
        "acpjournals":    _parse_acpjournals,
        "ahajournals":    _parse_ahajournals,
        "jacc":           _parse_jacc,
        "chest":          _parse_generic,
        "asco":           _parse_generic,
        "blood":          _parse_generic,
        "diabetesjournals": _parse_generic,
    }

    parser = parsers.get(publisher, _parse_generic)
    return parser(soup, toc_url)


# ── NEJM ──────────────────────────────────────────────────────────────────────

def _parse_nejm(soup: BeautifulSoup, base_url: str) -> TocResult:
    # Issue label from <div class="issue-meta"> or <h1 class="f-ui-1">
    label_tag = (
        soup.select_one("div.issue-meta")
        or soup.select_one(".m-issue-header")
        or soup.select_one("h1")
    )
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    for teaser in soup.select("div.o-article-teaser, div.m-article-teaser, article.o-teaser"):
        title_tag = teaser.select_one("h3 a, h4 a, .o-teaser__title a")
        if not title_tag or not title_tag.get_text(strip=True):
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = href if href.startswith("http") else f"https://www.nejm.org{href}"

        authors = [a.get_text(strip=True) for a in teaser.select(".o-author-list a, .author-list a")]
        atype_tag = teaser.select_one(".o-teaser__subtitle, .article-type, .m-article-type")
        article_type = atype_tag.get_text(strip=True) if atype_tag else ""
        doi_match = re.search(r"10\.\d{4}/\S+", url)
        doi = doi_match.group(0) if doi_match else None

        articles.append({
            "url": url,
            "title": title,
            "authors": authors,
            "article_type": article_type,
            "doi": doi,
            "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── JAMA ──────────────────────────────────────────────────────────────────────

def _parse_jama(soup: BeautifulSoup, base_url: str) -> TocResult:
    label_tag = soup.select_one(".issue-header, .current-issue-meta, h1.issue-title")
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    for item in soup.select("div.article-feed article, div.content-item, li.search-result-item"):
        title_tag = item.select_one("h3 a, h4 a, .article-title a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = href if href.startswith("http") else f"https://jamanetwork.com{href}"

        authors = [a.get_text(strip=True) for a in item.select(".contrib-author, .author-name")]
        atype_tag = item.select_one(".content-type, .article-type")
        article_type = atype_tag.get_text(strip=True) if atype_tag else ""

        articles.append({
            "url": url,
            "title": title,
            "authors": authors,
            "article_type": article_type,
            "doi": None,
            "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── Lancet ────────────────────────────────────────────────────────────────────

def _parse_lancet(soup: BeautifulSoup, base_url: str) -> TocResult:
    label_tag = soup.select_one(".issue-info, .current-issue-head, .vol-iss-date")
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    for item in soup.select("article.article-item, div.article-list-item, .toc-item"):
        title_tag = item.select_one("h3 a, h4 a, .article-title a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = href if href.startswith("http") else f"https://www.thelancet.com{href}"

        authors = [a.get_text(strip=True) for a in item.select(".author-name, .contrib-group a")]
        atype_tag = item.select_one(".article-type, .content-type")
        article_type = atype_tag.get_text(strip=True) if atype_tag else ""

        articles.append({
            "url": url, "title": title, "authors": authors,
            "article_type": article_type, "doi": None, "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── Nature ────────────────────────────────────────────────────────────────────

def _parse_nature(soup: BeautifulSoup, base_url: str) -> TocResult:
    label_tag = soup.select_one(".c-current-issue__info, .issue-meta, .c-hero__intro")
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    for item in soup.select("article.c-card, article.u-full-height"):
        title_tag = item.select_one("h3 a, h2 a, .c-card__title a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = href if href.startswith("http") else f"https://www.nature.com{href}"

        authors = [a.get_text(strip=True) for a in item.select(".c-author-list a, .authors a")]
        atype_tag = item.select_one(".c-meta__type, .article-type")
        article_type = atype_tag.get_text(strip=True) if atype_tag else ""
        doi_match = re.search(r"10\.\d{4}/\S+", url)
        doi = doi_match.group(0) if doi_match else None

        articles.append({
            "url": url, "title": title, "authors": authors,
            "article_type": article_type, "doi": doi, "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── BMJ ───────────────────────────────────────────────────────────────────────

def _parse_bmj(soup: BeautifulSoup, base_url: str) -> TocResult:
    label_tag = soup.select_one(".issue-meta, .highwire-cite-volume-issue")
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    for item in soup.select(".toc-section article, .highwire-article-citation"):
        title_tag = item.select_one("h3 a, h4 a, .highwire-cite-title a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = href if href.startswith("http") else f"https://www.bmj.com{href}"

        authors = [a.get_text(strip=True) for a in item.select(".highwire-citation-authors a")]
        atype_tag = item.select_one(".highwire-article-type, .article-type")
        article_type = atype_tag.get_text(strip=True) if atype_tag else ""

        articles.append({
            "url": url, "title": title, "authors": authors,
            "article_type": article_type, "doi": None, "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── ACP Journals (Annals of Internal Medicine) ────────────────────────────────

def _parse_acpjournals(soup: BeautifulSoup, base_url: str) -> TocResult:
    label_tag = soup.select_one(".issue-info, .current-issue-volume")
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    for item in soup.select("article, .toc-item, .issue-item"):
        title_tag = item.select_one("h3 a, h4 a, .article-title a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = href if href.startswith("http") else f"https://www.acpjournals.org{href}"

        authors = [a.get_text(strip=True) for a in item.select(".author-list a")]
        article_type = ""

        articles.append({
            "url": url, "title": title, "authors": authors,
            "article_type": article_type, "doi": None, "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── AHA Journals (Circulation) ────────────────────────────────────────────────

def _parse_ahajournals(soup: BeautifulSoup, base_url: str) -> TocResult:
    label_tag = soup.select_one(".issue-header, .toc-issue-info")
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    for item in soup.select(".toc-item, article.search-result-item"):
        title_tag = item.select_one("h3 a, h4 a, .article-title a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = href if href.startswith("http") else f"https://www.ahajournals.org{href}"

        authors = [a.get_text(strip=True) for a in item.select(".author-name, .contrib-author")]
        article_type = ""

        articles.append({
            "url": url, "title": title, "authors": authors,
            "article_type": article_type, "doi": None, "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── JACC ──────────────────────────────────────────────────────────────────────

def _parse_jacc(soup: BeautifulSoup, base_url: str) -> TocResult:
    return _parse_generic(soup, base_url, host="https://www.jacc.org")


# ── Generic fallback ──────────────────────────────────────────────────────────

def _parse_generic(soup: BeautifulSoup, base_url: str, host: str | None = None) -> TocResult:
    """
    Best-effort parser for unknown publishers.
    Looks for common article-listing patterns.
    """
    from urllib.parse import urlparse
    if host is None:
        parsed = urlparse(base_url)
        host = f"{parsed.scheme}://{parsed.netloc}"

    label_tag = (
        soup.select_one(".issue-header")
        or soup.select_one(".current-issue")
        or soup.select_one("h1")
    )
    issue_label = label_tag.get_text(" ", strip=True) if label_tag else ""

    articles = []
    seen = set()
    for tag in soup.select("h3 a[href], h4 a[href]"):
        href = tag.get("href", "")
        if not href or href.startswith("#"):
            continue
        url = href if href.startswith("http") else f"{host}{href}"
        if url in seen:
            continue
        seen.add(url)
        title = tag.get_text(strip=True)
        if len(title) < 10:
            continue
        articles.append({
            "url": url, "title": title, "authors": [],
            "article_type": "", "doi": None, "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_label(s: str) -> str:
    """Collapse whitespace, replace multiple spaces/newlines with a single space."""
    return re.sub(r"\s+", " ", s).strip()
```

- [ ] **Step 3: Manual smoke test — confirm a real scrape works for NEJM**

```bash
python -c "
from journal_club.toc_scraper import scrape
r = scrape('nejm', 'https://www.nejm.org/toc/nejm/current')
print('Label:', r.issue_label)
print('Articles:', len(r.articles))
for a in r.articles[:3]:
    print(' -', a['article_type'], '|', a['title'][:60])
"
```

Expected: label with volume/issue info and at least 5 articles listed. If 0 articles are returned, the HTML structure has changed — inspect `soup.prettify()[:3000]` and update the selector in `_parse_nejm`.

- [ ] **Step 4: Commit**

```bash
git add journal_club/toc_scraper.py
git commit -m "feat: add publisher-specific TOC scrapers (NEJM, JAMA, Lancet, Nature, BMJ, AHA, ACP)"
```

---

## Task 4: Mailer

**Files:**
- Create: `journal_club/mailer.py`

Sends an email with Reading List article titles (as text) and any downloaded PDFs attached.

- [ ] **Step 1: Create `journal_club/mailer.py`**

```python
# journal_club/mailer.py
"""
Send the reading list as an email with PDF attachments.
Uses stdlib smtplib (no external dependency).
"""
from __future__ import annotations

import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path


def send_reading_list(
    articles: list[dict],
    to_addr: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
) -> int:
    """
    Build and send the reading-list email.
    articles: list of dicts from storage.get_reading_list()
    Returns number of PDF attachments included.
    """
    msg = MIMEMultipart()
    msg["Subject"] = f"Journal Club Reading List ({len(articles)} articles)"
    msg["From"] = smtp_user
    msg["To"] = to_addr

    # Build plain-text body
    lines = ["Your Journal Club reading list:\n"]
    for i, a in enumerate(articles, 1):
        authors_str = ", ".join(a.get("authors", [])[:3])
        if len(a.get("authors", [])) > 3:
            authors_str += " et al."
        pdf_note = "(PDF attached)" if a.get("pdf_path") else "(PDF not yet downloaded)"
        lines.append(f"{i}. {a['title']}")
        lines.append(f"   {a.get('journal_name', '')} · {a.get('issue_label', '')}")
        if authors_str:
            lines.append(f"   {authors_str}")
        lines.append(f"   {a.get('url', '')} {pdf_note}")
        lines.append("")

    msg.attach(MIMEText("\n".join(lines), "plain", "utf-8"))

    # Attach PDFs
    attached = 0
    for a in articles:
        pdf_path = a.get("pdf_path")
        if not pdf_path:
            continue
        p = Path(pdf_path)
        if not p.exists():
            continue
        part = MIMEBase("application", "pdf")
        part.set_payload(p.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=p.name)
        msg.attach(part)
        attached += 1

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_addr, msg.as_string())

    return attached
```

- [ ] **Step 2: Commit**

```bash
git add journal_club/mailer.py
git commit -m "feat: add mailer for reading list email with PDF attachments"
```

---

## Task 5: Config — add email fields

**Files:**
- Modify: `journal_club/config.py`
- Modify: `config.yaml`

- [ ] **Step 1: Update `journal_club/config.py`**

```python
from dataclasses import dataclass
import yaml


@dataclass
class Config:
    huji_email: str
    huji_password: str
    output_dir: str
    chrome_profile: str
    chrome_path: str = ""
    email_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""


def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(
        huji_email=data["huji_email"],
        huji_password=data["huji_password"],
        output_dir=data["output_dir"],
        chrome_profile=data["chrome_profile"],
        chrome_path=data.get("chrome_path", ""),
        email_to=data.get("email_to", ""),
        smtp_host=data.get("smtp_host", "smtp.gmail.com"),
        smtp_port=int(data.get("smtp_port", 587)),
        smtp_user=data.get("smtp_user", ""),
        smtp_password=data.get("smtp_password", ""),
    )
```

- [ ] **Step 2: Add email fields to `config.yaml`**

Add these lines to `config.yaml` (leave values blank for now; user fills in their own):

```yaml
# Email — Reading List
email_to: ""          # address to send reading list to
smtp_host: smtp.gmail.com
smtp_port: 587
smtp_user: ""         # Gmail address (use an App Password, not account password)
smtp_password: ""     # Gmail App Password
```

- [ ] **Step 3: Commit**

```bash
git add journal_club/config.py config.yaml
git commit -m "feat: add email/SMTP fields to Config"
```

---

## Task 6: Flask Routes

**Files:**
- Modify: `app.py`

Add all journals + reading list routes, and the APScheduler weekly job.

- [ ] **Step 1: Install APScheduler**

```bash
pip install apscheduler
```

Expected: `Successfully installed apscheduler-...`

- [ ] **Step 2: Replace `app.py` with the updated version**

```python
#!/usr/bin/env python3
"""
Journal Club — Flask web app
Usage: python app.py
Then open http://localhost:5000
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

from journal_club.config import load_config
from journal_club.resolver import resolve
from journal_club.journals_catalog import CATALOG
from journal_club.toc_scraper import scrape
from journal_club.mailer import send_reading_list
import journal_club.storage as storage

app = Flask(__name__)
cfg = load_config("config.yaml")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _refresh_journal(journal: dict) -> None:
    """Scrape TOC for a single journal and persist to DB. Safe to call in any thread."""
    try:
        # Determine publisher from catalog (match by toc_url)
        publisher = next(
            (e.publisher for e in CATALOG if e.toc_url == journal["toc_url"]),
            "generic",
        )
        result = scrape(publisher, journal["toc_url"])
        old_label = journal.get("current_issue_label", "")
        is_new = bool(result.issue_label and result.issue_label != old_label)
        storage.update_journal_toc(journal["id"], result.issue_label, result.articles, is_new)
        print(f"[TOC] {journal['name']}: {len(result.articles)} articles. New={is_new}")
    except Exception as e:
        print(f"[TOC] Failed to refresh {journal['name']}: {e}")


def _refresh_all_journals() -> None:
    for j in storage.get_journals():
        _refresh_journal(j)


# ── Scheduler — weekly TOC refresh ───────────────────────────────────────────

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(_refresh_all_journals, "interval", weeks=1, id="weekly_toc_refresh")
scheduler.start()


# ── Existing routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("add"))


@app.route("/add")
def add():
    return render_template("add_article.html", page="add")


@app.route("/history")
def history():
    articles = storage.get_history()
    return render_template("history.html", articles=articles, page="history")


@app.route("/bookmarks")
def bookmarks():
    articles = storage.get_bookmarks()
    return render_template("bookmarks.html", articles=articles, page="bookmarks")


@app.route("/article/<int:article_id>")
def article(article_id: int):
    a = storage.get_by_id(article_id)
    if a is None:
        return "Article not found", 404
    if request.headers.get("Accept") == "application/json":
        return jsonify(a)
    return render_template("article.html", article=a, page="history")


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json(force=True)
    input_str = (data or {}).get("input", "").strip()
    toc_article_id = (data or {}).get("toc_article_id")
    if not input_str:
        return jsonify({"error": "No input provided"}), 400

    try:
        meta = resolve(input_str)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    article_id = storage.save_article(meta, pdf_path=None)

    def _run():
        try:
            from download import download_article
            _, pdf_path = download_article(meta.url, cfg)
            storage.update_pdf_path(article_id, pdf_path)
            if toc_article_id:
                storage.link_reading_list_to_article(toc_article_id, article_id)
        except Exception as e:
            print(f"[Download thread] Error: {e}")

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({
        "article_id": article_id,
        "title": meta.title or meta.url,
        "url": meta.url,
    })


@app.route("/bookmark/<int:article_id>", methods=["POST"])
def bookmark(article_id: int):
    new_state = storage.toggle_bookmark(article_id)
    return jsonify({"bookmarked": new_state})


# ── Journals routes ───────────────────────────────────────────────────────────

@app.route("/journals")
def journals():
    followed = storage.get_journals()
    followed_urls = {j["toc_url"] for j in followed}
    catalog = [
        {"name": e.name, "publisher": e.publisher, "toc_url": e.toc_url, "issn": e.issn}
        for e in CATALOG
        if e.toc_url not in followed_urls
    ]
    # Preselect first followed journal
    selected_id = request.args.get("selected", type=int)
    if selected_id is None and followed:
        selected_id = followed[0]["id"]
    toc_articles = storage.get_toc_articles(selected_id) if selected_id else []
    reading_list_ids = storage.get_reading_list_ids()
    selected_journal = next((j for j in followed if j["id"] == selected_id), None)
    return render_template(
        "journals.html",
        page="journals",
        followed=followed,
        catalog=catalog,
        selected_id=selected_id,
        selected_journal=selected_journal,
        toc_articles=toc_articles,
        reading_list_ids=reading_list_ids,
    )


@app.route("/journals/add", methods=["POST"])
def journals_add():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    publisher = data.get("publisher", "generic").strip()
    toc_url = data.get("toc_url", "").strip()
    issn = data.get("issn") or None

    if not name or not toc_url:
        return jsonify({"error": "name and toc_url are required"}), 400

    journal_id = storage.add_journal(name, publisher, toc_url, issn)
    # Trigger an immediate TOC fetch in background
    j = storage.get_journal(journal_id)
    threading.Thread(target=_refresh_journal, args=(j,), daemon=True).start()
    return jsonify({"journal_id": journal_id, "name": name})


@app.route("/journals/<int:journal_id>/refresh", methods=["POST"])
def journals_refresh(journal_id: int):
    j = storage.get_journal(journal_id)
    if j is None:
        return jsonify({"error": "Journal not found"}), 404
    threading.Thread(target=_refresh_journal, args=(j,), daemon=True).start()
    return jsonify({"status": "refreshing"})


@app.route("/journals/<int:journal_id>", methods=["DELETE"])
def journals_delete(journal_id: int):
    storage.remove_journal(journal_id)
    return jsonify({"status": "removed"})


@app.route("/journals/<int:journal_id>/toc")
def journals_toc(journal_id: int):
    articles = storage.get_toc_articles(journal_id)
    reading_list_ids = storage.get_reading_list_ids()
    for a in articles:
        a["in_reading_list"] = a["id"] in reading_list_ids
    return jsonify(articles)


# ── Reading List routes ───────────────────────────────────────────────────────

@app.route("/reading-list")
def reading_list_page():
    items = storage.get_reading_list()
    return jsonify(items)   # Used by the frontend JS


@app.route("/reading-list/add", methods=["POST"])
def reading_list_add():
    data = request.get_json(force=True) or {}
    toc_article_id = data.get("toc_article_id")
    if not toc_article_id:
        return jsonify({"error": "toc_article_id required"}), 400
    storage.add_to_reading_list(toc_article_id)
    return jsonify({"status": "added"})


@app.route("/reading-list/remove", methods=["POST"])
def reading_list_remove():
    data = request.get_json(force=True) or {}
    toc_article_id = data.get("toc_article_id")
    if not toc_article_id:
        return jsonify({"error": "toc_article_id required"}), 400
    storage.remove_from_reading_list(toc_article_id)
    return jsonify({"status": "removed"})


@app.route("/reading-list/email", methods=["POST"])
def reading_list_email():
    if not cfg.email_to or not cfg.smtp_user or not cfg.smtp_password:
        return jsonify({"error": "Email not configured in config.yaml"}), 400
    items = storage.get_reading_list()
    if not items:
        return jsonify({"error": "Reading list is empty"}), 400
    try:
        attached = send_reading_list(
            articles=items,
            to_addr=cfg.email_to,
            smtp_host=cfg.smtp_host,
            smtp_port=cfg.smtp_port,
            smtp_user=cfg.smtp_user,
            smtp_password=cfg.smtp_password,
        )
        return jsonify({"status": "sent", "articles": len(items), "pdfs_attached": attached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
```

- [ ] **Step 3: Verify app starts without errors**

```bash
python app.py &
sleep 3
curl -s http://localhost:5000/ | head -5
```

Expected: HTML redirect or redirect response with no Python tracebacks.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add journals and reading-list Flask routes + weekly APScheduler"
```

---

## Task 7: Journals Template

**Files:**
- Create: `templates/journals.html`

Two-panel layout: journal list (left), selected journal's TOC (right).

- [ ] **Step 1: Create `templates/journals.html`**

```html
{% extends "base.html" %}
{% block title %}Journals · Journal Club{% endblock %}

{% block content %}
<div class="flex h-screen overflow-hidden">

  <!-- LEFT PANEL: followed journals list -->
  <aside class="w-72 flex-shrink-0 border-r border-slate-200 bg-slate-50 flex flex-col overflow-hidden">
    <div class="px-4 pt-6 pb-3 border-b border-slate-200">
      <h2 class="font-headline text-base font-bold text-primary">Following</h2>
      <p class="text-xs text-slate-400 mt-0.5">{{ followed|length }} journal{{ 's' if followed|length != 1 }}</p>
    </div>

    <!-- Journal list -->
    <ul class="flex-1 overflow-y-auto py-2" id="journal-list">
      {% for j in followed %}
      <li>
        <button
          onclick="selectJournal({{ j.id }})"
          class="journal-btn w-full text-left px-4 py-3 flex items-center gap-2 hover:bg-slate-100 transition-colors
                 {% if j.id == selected_id %}bg-primary/10 border-l-2 border-primary{% else %}border-l-2 border-transparent{% endif %}"
          data-id="{{ j.id }}">
          {% if j.has_new_issue %}
          <span class="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" title="New issue"></span>
          {% else %}
          <span class="w-2 h-2 rounded-full bg-transparent flex-shrink-0"></span>
          {% endif %}
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-sm text-on-surface truncate">{{ j.name }}</div>
            {% if j.current_issue_label %}
            <div class="text-xs text-slate-400 truncate">{{ j.current_issue_label }}</div>
            {% elif j.last_checked %}
            <div class="text-xs text-slate-400">Checking…</div>
            {% else %}
            <div class="text-xs text-slate-400">Never checked</div>
            {% endif %}
          </div>
          <button
            onclick="event.stopPropagation(); removeJournal({{ j.id }}, this)"
            class="text-slate-300 hover:text-red-400 transition-colors ml-1"
            title="Unfollow">
            <span class="material-symbols-outlined text-base">close</span>
          </button>
        </button>
      </li>
      {% endfor %}
    </ul>

    <!-- Add journal button -->
    <div class="p-3 border-t border-slate-200">
      <button onclick="openAddModal()"
        class="w-full flex items-center justify-center gap-2 py-2 rounded bg-primary text-white text-sm font-semibold hover:bg-primary-container transition-colors">
        <span class="material-symbols-outlined text-base">add</span>
        Add journal
      </button>
    </div>
  </aside>

  <!-- RIGHT PANEL: TOC -->
  <div class="flex-1 overflow-y-auto">
    {% if selected_journal %}
    <div class="px-6 pt-6 pb-3 flex items-start justify-between border-b border-slate-200 sticky top-0 bg-white z-10">
      <div>
        <h1 class="font-headline text-lg font-bold text-on-surface">{{ selected_journal.name }}</h1>
        <p class="text-sm text-slate-400 mt-0.5">{{ selected_journal.current_issue_label or 'Fetching current issue…' }}</p>
      </div>
      <div class="flex items-center gap-2 mt-1">
        <!-- Reading list email button -->
        <button onclick="emailReadingList()"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded border border-primary text-primary text-sm font-semibold hover:bg-primary/5 transition-colors"
          id="email-btn">
          <span class="material-symbols-outlined text-base">mail</span>
          Email reading list
        </button>
        <!-- Refresh button -->
        <button onclick="refreshJournal({{ selected_journal.id }})"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded border border-slate-200 text-slate-500 text-sm font-semibold hover:bg-slate-50 transition-colors"
          id="refresh-btn">
          <span class="material-symbols-outlined text-base" id="refresh-icon">refresh</span>
          Refresh now
        </button>
      </div>
    </div>

    <!-- TOC article list -->
    <div class="px-6 py-4 space-y-2" id="toc-list">
      {% for a in toc_articles %}
      {% set in_rl = a.id in reading_list_ids %}
      <div class="toc-article border border-slate-200 rounded-lg bg-white" data-id="{{ a.id }}">
        <!-- Collapsed row -->
        <div class="px-4 py-3 flex items-start gap-3 cursor-pointer hover:bg-slate-50 transition-colors"
             onclick="toggleArticle(this)">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap mb-0.5">
              {% if a.article_type %}
              <span class="text-xs font-label font-medium text-secondary uppercase tracking-wide">{{ a.article_type }}</span>
              {% endif %}
            </div>
            <p class="font-semibold text-sm text-on-surface leading-snug">{{ a.title }}</p>
            {% if a.authors %}
            <p class="text-xs text-slate-400 mt-0.5">
              {{ a.authors[:3] | join(', ') }}{% if a.authors | length > 3 %} et al.{% endif %}
            </p>
            {% endif %}
          </div>
          <div class="flex items-center gap-2 flex-shrink-0 mt-0.5">
            <!-- Reading list toggle -->
            <button onclick="event.stopPropagation(); toggleReadingList({{ a.id }}, this)"
              class="rl-btn flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-semibold border transition-colors
                     {% if in_rl %}bg-primary/10 text-primary border-primary/30{% else %}border-slate-200 text-slate-500 hover:border-primary hover:text-primary{% endif %}"
              data-in-rl="{{ 'true' if in_rl else 'false' }}"
              title="{% if in_rl %}Remove from reading list{% else %}Add to reading list{% endif %}">
              <span class="material-symbols-outlined text-sm">{% if in_rl %}mark_email_read{% else %}mail{% endif %}</span>
              {% if in_rl %}In list{% else %}Reading list{% endif %}
            </button>
            <!-- PDF download -->
            <button onclick="event.stopPropagation(); downloadPdf('{{ a.url }}', {{ a.id }}, this)"
              class="pdf-btn flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-semibold bg-primary text-white hover:bg-primary-container transition-colors">
              <span class="material-symbols-outlined text-sm">download</span>
              PDF
            </button>
          </div>
        </div>
        <!-- Expanded: abstract -->
        <div class="article-detail hidden px-4 pb-4">
          {% if a.abstract %}
          <p class="text-sm text-on-surface-variant leading-relaxed border-t border-slate-100 pt-3">{{ a.abstract }}</p>
          {% else %}
          <p class="text-sm text-slate-400 italic border-t border-slate-100 pt-3">No abstract available.</p>
          {% endif %}
          <a href="{{ a.url }}" target="_blank"
             class="inline-flex items-center gap-1 mt-2 text-xs text-primary hover:underline">
            <span class="material-symbols-outlined text-sm">open_in_new</span>
            Open article page
          </a>
        </div>
      </div>
      {% else %}
      <div class="text-center py-16 text-slate-400">
        <span class="material-symbols-outlined text-4xl block mb-2">article</span>
        <p class="text-sm">No articles yet — click Refresh now to fetch the current issue.</p>
      </div>
      {% endfor %}
    </div>

    {% else %}
    <div class="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
      <span class="material-symbols-outlined text-5xl">library_books</span>
      <p class="text-base font-semibold">No journals followed yet</p>
      <p class="text-sm">Click "Add journal" to get started.</p>
    </div>
    {% endif %}
  </div>
</div>

<!-- Add Journal Modal -->
<div id="add-modal" class="fixed inset-0 bg-black/40 z-50 hidden flex items-center justify-center">
  <div class="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 overflow-hidden">
    <div class="px-6 pt-5 pb-4 border-b border-slate-200 flex items-center justify-between">
      <h3 class="font-headline font-bold text-base text-on-surface">Add a Journal</h3>
      <button onclick="closeAddModal()" class="text-slate-400 hover:text-slate-600">
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>
    <div class="px-6 py-4">
      <!-- Search catalog -->
      <input type="text" id="catalog-search" placeholder="Search journals…"
        oninput="filterCatalog(this.value)"
        class="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-primary mb-3">
      <ul id="catalog-list" class="space-y-1 max-h-60 overflow-y-auto">
        {% for e in catalog %}
        <li class="catalog-item flex items-center justify-between px-3 py-2 rounded hover:bg-slate-50"
            data-name="{{ e.name | lower }}">
          <div>
            <div class="text-sm font-semibold text-on-surface">{{ e.name }}</div>
            <div class="text-xs text-slate-400">{{ e.publisher }}</div>
          </div>
          <button onclick="followCatalog('{{ e.name }}','{{ e.publisher }}','{{ e.toc_url }}','{{ e.issn or '' }}')"
            class="text-xs font-semibold text-primary hover:underline">Follow</button>
        </li>
        {% endfor %}
      </ul>

      <!-- Custom URL fallback -->
      <div class="mt-4 pt-4 border-t border-slate-200">
        <p class="text-xs text-slate-400 mb-2">Not listed? Paste the journal's "current issue" page URL:</p>
        <div class="flex gap-2">
          <input type="text" id="custom-url" placeholder="https://journal.example.com/current"
            class="flex-1 border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-primary">
          <input type="text" id="custom-name" placeholder="Journal name"
            class="w-36 border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-primary">
        </div>
        <button onclick="followCustom()"
          class="mt-2 w-full py-2 rounded bg-primary text-white text-sm font-semibold hover:bg-primary-container transition-colors">
          Follow this URL
        </button>
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const SELECTED_ID = {{ selected_id or 'null' }};

// ── Expand/collapse article row ───────────────────────────────────────────────
function toggleArticle(header) {
  const detail = header.nextElementSibling;
  detail.classList.toggle('hidden');
}

// ── Select a journal (reload page with ?selected=) ────────────────────────────
function selectJournal(id) {
  window.location = '/journals?selected=' + id;
}

// ── Refresh journal TOC ───────────────────────────────────────────────────────
function refreshJournal(id) {
  const btn = document.getElementById('refresh-btn');
  const icon = document.getElementById('refresh-icon');
  btn.disabled = true;
  icon.classList.add('animate-spin');
  fetch('/journals/' + id + '/refresh', {method: 'POST'})
    .then(() => {
      // Poll until last_checked changes (simplified: just reload after 8s)
      setTimeout(() => window.location.reload(), 8000);
    })
    .catch(e => { console.error(e); btn.disabled = false; });
}

// ── Toggle reading list ───────────────────────────────────────────────────────
function toggleReadingList(tocArticleId, btn) {
  const inRL = btn.dataset.inRl === 'true';
  const url = inRL ? '/reading-list/remove' : '/reading-list/add';
  fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({toc_article_id: tocArticleId}),
  }).then(r => r.json()).then(() => {
    if (inRL) {
      btn.dataset.inRl = 'false';
      btn.className = btn.className.replace('bg-primary/10 text-primary border-primary/30', 'border-slate-200 text-slate-500 hover:border-primary hover:text-primary');
      btn.innerHTML = '<span class="material-symbols-outlined text-sm">mail</span> Reading list';
    } else {
      btn.dataset.inRl = 'true';
      btn.className = btn.className.replace('border-slate-200 text-slate-500 hover:border-primary hover:text-primary', 'bg-primary/10 text-primary border-primary/30');
      btn.innerHTML = '<span class="material-symbols-outlined text-sm">mark_email_read</span> In list';
    }
  });
}

// ── Download PDF ──────────────────────────────────────────────────────────────
function downloadPdf(url, tocArticleId, btn) {
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined text-sm animate-spin">progress_activity</span> Downloading…';
  fetch('/download', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({input: url, toc_article_id: tocArticleId}),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      btn.disabled = false;
      btn.innerHTML = '<span class="material-symbols-outlined text-sm">error</span> Failed';
      return;
    }
    btn.innerHTML = '<span class="material-symbols-outlined text-sm">check</span> Queued';
  });
}

// ── Email reading list ────────────────────────────────────────────────────────
function emailReadingList() {
  const btn = document.getElementById('email-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined text-base">hourglass_empty</span> Sending…';
  fetch('/reading-list/email', {method: 'POST'})
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        btn.innerHTML = '<span class="material-symbols-outlined text-base">error</span> ' + data.error;
        setTimeout(() => { btn.disabled=false; btn.innerHTML='<span class="material-symbols-outlined text-base">mail</span> Email reading list'; }, 4000);
      } else {
        btn.innerHTML = '<span class="material-symbols-outlined text-base">check_circle</span> Sent!';
        setTimeout(() => { btn.disabled=false; btn.innerHTML='<span class="material-symbols-outlined text-base">mail</span> Email reading list'; }, 3000);
      }
    });
}

// ── Add journal modal ─────────────────────────────────────────────────────────
function openAddModal()  { document.getElementById('add-modal').classList.remove('hidden'); }
function closeAddModal() { document.getElementById('add-modal').classList.add('hidden'); }

function filterCatalog(q) {
  document.querySelectorAll('.catalog-item').forEach(li => {
    li.style.display = li.dataset.name.includes(q.toLowerCase()) ? '' : 'none';
  });
}

function followCatalog(name, publisher, toc_url, issn) {
  fetch('/journals/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, publisher, toc_url, issn: issn || null}),
  }).then(r => r.json()).then(data => {
    if (data.journal_id) window.location = '/journals?selected=' + data.journal_id;
  });
}

function followCustom() {
  const toc_url = document.getElementById('custom-url').value.trim();
  const name = document.getElementById('custom-name').value.trim();
  if (!toc_url || !name) { alert('Please enter both a URL and a name.'); return; }
  fetch('/journals/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, publisher: 'generic', toc_url, issn: null}),
  }).then(r => r.json()).then(data => {
    if (data.journal_id) window.location = '/journals?selected=' + data.journal_id;
  });
}

function removeJournal(id, btn) {
  if (!confirm('Unfollow this journal?')) return;
  fetch('/journals/' + id, {method: 'DELETE'})
    .then(() => window.location = '/journals');
}

// Close modal when clicking backdrop
document.getElementById('add-modal').addEventListener('click', function(e) {
  if (e.target === this) closeAddModal();
});
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/journals.html
git commit -m "feat: add two-panel journals template with TOC, reading list, and add-journal modal"
```

---

## Task 8: Nav + Cleanup

**Files:**
- Modify: `templates/base.html`

Add the Journals nav item between "Add Article" and "History".

- [ ] **Step 1: Add Journals nav item in `templates/base.html`**

In the `<nav>` block, insert after the "Add Article" `<a>` tag and before the "History" `<a>` tag:

```html
      <a href="/journals"
         class="flex items-center gap-3 px-3 py-2.5 rounded font-body font-semibold text-sm transition-colors
                {% if page == 'journals' %}bg-primary/10 text-primary{% else %}text-slate-500 hover:bg-slate-100{% endif %}">
        <span class="material-symbols-outlined {% if page == 'journals' %}fill-icon{% endif %}">library_books</span>
        <span>Journals</span>
      </a>
```

- [ ] **Step 2: Verify all pages load**

```bash
python app.py &
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/journals
```

Expected: `200`

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add Journals nav item to sidebar"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Two-panel layout (journal list left, TOC right) — Task 7
- [x] Curated catalog of ~15 journals + free-form URL fallback — Tasks 2 + 7 (modal)
- [x] Weekly auto-refresh + manual refresh button — Task 6 (APScheduler + `/journals/<id>/refresh`)
- [x] Green dot for new issues — Task 7 (template: `has_new_issue` flag)
- [x] Expandable article rows with abstract — Task 7 (toggle function)
- [x] PDF download from TOC — Task 7 (`downloadPdf` → `/download` with `toc_article_id`)
- [x] Reading list add/remove per article — Tasks 1 + 6 + 7
- [x] "Email reading list" manual send button — Tasks 4 + 6 + 7
- [x] Config email fields — Task 5

**Placeholder scan:** No TBDs or TODOs found in code blocks.

**Type consistency:** `toc_article_id` used consistently in storage, routes, and template JS. `journal_id` consistent throughout. `TocResult.articles` is `list[dict]` everywhere.
