# Journal Club App — Development Guide

## Session Focus
**This session targets the macOS (darwin) version only.** All changes must work correctly on Mac. Windows-only code paths (`taskkill`, `powershell`, `icacls`, `%LOCALAPPDATA%`) should be preserved but not extended — add `sys.platform == "win32"` or `cfg!(target_os = "windows")` guards instead.

---

## Overview

A Flask web app for curating, downloading, and sharing academic journal articles. Users follow journals, view table-of-contents (TOC), download PDFs, manage a reading list, and email selected articles via Resend.

**Current branch:** `feature/journal-club-downloader`

---

## Architecture

### Core Stack
- **Backend:** Flask + APScheduler (weekly TOC refresh)
- **Database:** SQLite with WAL mode (`journal_club.db`)
- **PDF Download:** Selenium + Chrome (headless)
- **Email:** Resend API (not SMTP)
- **Styling:** Tailwind CSS (CDN) with custom dark mode

### Key Modules

#### `journal_club/`

- **`config.py`**: Config dataclass, YAML loader. Fields: `huji_email`, `huji_password`, `output_dir`, `chrome_profile`, `resend_api_key`, `resend_from`, `email_to_1/2/3`, `admin_password`
  
- **`storage.py`**: SQLite ORM layer. Tables:
  - `articles` — downloaded PDFs with metadata
  - `journals` — followed journals (has_new_issue, current_issue_label)
  - `toc_articles` — TOC entries (issue_label, doi, url, title, journal, authors, abstract)
  - `reading_list` — selected articles for bulk email
  - `settings` — key-value store for runtime overrides
  
  Key methods: `get_journals()`, `update_journal_toc()`, `add_to_reading_list()`, `get_reading_list()`

- **`journals_catalog.py`**: 15+ curated journals (NEJM, JAMA, Lancet, Nature Medicine, BMJ, etc.) as frozen dataclasses with name, publisher, toc_url, issn.

- **`toc_scraper.py`**: Publisher-specific HTML parsers + PubMed API fallback.
  - Tries HTML scrape first (BeautifulSoup)
  - Falls back to PubMed eutils (esearch → esummary → efetch) if HTML yields 0 articles and ISSN available
  - Handles Elsevier 403 gracefully

- **`router.py`**: Detects publisher from URL/DOI. Maps to auth paths (OPENATHENS, ELSEVIER, JAMA, etc.).
  - **Recent fix:** Added DOI prefix detection (`10.1016`, `10.1001`, `10.1007`, etc.) before domain rules so `doi.org/10.1016/...` routes to ELSEVIER, not OPENATHENS_GENERIC

- **`resolver.py`**: Classifies input (PMID, PubMed URL, DOI, article URL) and looks up metadata via PubMed.
  - Bare DOI (e.g., `10.1016/j.cell.2022.07.003`) triggers PubMed search and populates title/journal/authors
  - Direct URLs return minimal metadata (url only)

- **`mailer.py`**: Sends reading list via Resend API.
  - Signature: `send_reading_list(articles, api_key, from_addr, to_addrs) → int`
  - HTML email with styled table + base64 PDF attachments

#### `app.py`

- `get_runtime_config()` — reads from DB settings, falls back to `cfg` from YAML
- Admin routes (protected by `@require_admin` decorator, Flask sessions):
  - `GET /admin/login` — login form
  - `POST /admin/login` — authenticate (password from `cfg.admin_password`)
  - `POST /admin/logout` — clear session
  - `GET /admin/settings` — Resend API key + from address
  - `POST /admin/settings` — save Resend config to DB
- Main routes:
  - `GET /journals`, `POST /journals/add`, `GET /journals/<id>/refresh`, `DELETE /journals/<id>`, `GET /journals/<id>/toc`, `GET /journals/<id>/status`
  - `GET /reading-list`, `POST /reading-list/add`, `POST /reading-list/remove`, `POST /reading-list/email`
  - `GET /settings`, `POST /settings` — HUJI creds + recipients (no Resend)
  - `GET /download` — entry point for PDF download
- APScheduler job: `_refresh_all_journals()` weekly

#### `download.py`

- Selenium automation to download PDFs from paywalled journals
- **Known issue:** `input()` on line 105 raises `EOFError` in background threads (web mode) — caught and passed, but Chrome closes immediately. May need timeout/polling instead.

#### `templates/`

- **`base.html`**: Main layout with sidebar (nav, dark mode toggle, font size buttons, settings link). Dark mode via `.dark` class on `<html>`, font size via `.fs-sm/.fs-md/.fs-lg/.fs-xl`.

- **`journals.html`**: Two-panel layout.
  - Left: followed journal list with green dot (new issue), Add button, Remove button
  - Right: TOC articles (expandable rows showing abstract + PDF download + Reading list toggle)
  - Modal: add journal (search catalog or custom URL+name)
  - **Recent fix:** PDF button passes `{{ a.doi or a.url }}` so resolver does PubMed lookup for proper title/journal

- **`settings.html`**: User settings (HUJI email/password, 3 email recipients). Auto-save on Enter.

- **`admin_login.html`**: Admin login form (password from `config.yaml`).

- **`admin_settings.html`**: Admin-only Resend API key + from address. Requires session auth.

- **`history.html`**, **`bookmarks.html`**: Download history and bookmarks (not yet fully implemented).

---

## Key Features & Workflows

### 1. Follow a Journal
User clicks "Add Journal" → search catalog or enter custom URL + name → stored in DB with `has_new_issue=False`.

### 2. Weekly TOC Refresh
APScheduler runs `_refresh_all_journals()` every Sunday.
- For each journal: call `scrape(publisher, toc_url, issn)`
- HTML parser tries first (e.g., `_parse_nejm()`, `_parse_jama()`)
- If 0 articles, try PubMed via ISSN
- Store `toc_articles` in DB, set `has_new_issue=True` (cleared on view)

### 3. Download Article
From TOC, click PDF button → `/download?url=...&id=...&toc_article_id=...`
- `resolve(url)` classifies input
- `get_full_url(doi)` maps DOI to journal domain (NEJM, JAMA, Elsevier, etc.)
- `authenticate_*` methods handle login/OAuth
- Selenium downloads PDF to `output_dir`
- `link_reading_list_to_article()` associates TOC article if provided
- **Recent fix:** Button passes DOI instead of URL so PubMed lookup populates title/journal; fixes "Unknown Journal" in History

### 4. Reading List Email
User selects articles → clicks "Email reading list" → `send_reading_list()` via Resend.
- Requires Resend API key + from address (stored in DB, entered via `/admin/settings`)
- Sends to up to 3 recipients (via `email_to_1/2/3` in settings)
- HTML email with styled table + base64 PDF attachments

### 5. Admin Access
Only you can access `/admin/login` (password in `config.yaml`).
- Session-based auth: `session['is_admin'] = True` on correct password
- `/admin/settings` shows Resend config (hidden from regular users)
- Regular users see `/settings` (HUJI creds + recipients only)

---

## Configuration

### `config.yaml`
```yaml
huji_email: "..."
huji_password: "..."
admin_password: "changeme"           # for /admin/login
output_dir: "..."
chrome_profile: "..."
resend_api_key: ""                   # can be set via /admin/settings
resend_from: ""                      # can be set via /admin/settings
email_to_1: ""                       # set via /settings
email_to_2: ""
email_to_3: ""
```

### Database Settings
Runtime config can override YAML:
```python
get_runtime_config()  # reads from DB settings table, falls back to cfg
```

---

## Recent Fixes & Important Details

### 1. Router DOI Detection (commit: `fix: detect Elsevier/JAMA/Springer from doi.org redirect URLs`)
- **Problem:** `doi.org/10.1016/...` wasn't matched as ELSEVIER → fell through to OPENATHENS_GENERIC
- **Solution:** Added DOI prefix checks before domain rules in `detect_publisher()`
- **Impact:** Elsevier downloads now use correct auth path

### 2. DOI Fallback for Resolver (journals.html PDF button)
- **Problem:** Articles from TOC had URL but no DOI; resolver classifies URLs as direct (no PubMed lookup) → empty title/journal in History
- **Solution:** Pass DOI when available: `downloadPdf('{{ a.doi or a.url }}', ...)`
- **Impact:** PubMed lookup populates metadata; "Unknown Journal" resolved

### 3. PubMed Fallback for TOC Scraping
- **Problem:** Many publishers (Elsevier, Nature) block HTML scraping with 403
- **Solution:** `scrape()` tries HTML first, falls back to PubMed eutils if ISSN available
- **Impact:** AJOG and other blocked journals now work via PubMed

### 4. Admin Login System
- **Why:** Resend API key is sensitive; regular users shouldn't see it
- **How:** Session-based login, password from `config.yaml`, decorator `@require_admin`
- **Layout:** `/settings` (public) + `/admin/settings` (protected)

---

## Common Tasks

### Add a New Journal
1. Add entry to `journals_catalog.py` (CatalogEntry dataclass)
2. Ensure `publisher` and `toc_url` match a scraper in `toc_scraper.py`
3. If needed, write new parser function (e.g., `_parse_newjournal()`)

### Migrate Email Provider
- Currently Resend (API-based)
- To switch: edit `mailer.py` `send_reading_list()` function
- Store credentials in DB via `/admin/settings`

### Debug TOC Scraping
- Check `toc_scraper.py` for HTTP errors (caught gracefully, return empty TocResult)
- Verify ISSN is correct in `journals_catalog.py`
- PubMed fallback requires valid ISSN

### Test Downloads
- Use `/download?doi=10.1056/...` (DOI) to test resolver + auth
- Check `output_dir` for downloaded PDFs
- History page should show title/journal/authors (if DOI resolves via PubMed)

### Article-review agents
Run `/appraise <path-to-pdf>` to fan out to the eight peer-review lenses in
`.claude/agents/appraisal-*.md` (methodologist, statistician, claims-auditor,
clinical-relevance, integrity, writing, novelty, references) and print a
synthesized review report. Command defined in `.claude/commands/appraise.md`.

---

## Files Checklist

Core logic:
- ✅ `journal_club/config.py`, `storage.py`, `journals_catalog.py`, `toc_scraper.py`, `router.py`, `resolver.py`, `mailer.py`
- ✅ `app.py` (Flask routes, APScheduler, admin auth)
- ✅ `download.py` (Selenium)

Templates:
- ✅ `base.html` (sidebar, dark mode, layout)
- ✅ `journals.html` (main TOC UI)
- ✅ `settings.html` (user settings)
- ✅ `admin_login.html`, `admin_settings.html` (admin auth)
- 🔧 `history.html`, `bookmarks.html` (placeholder)

---

## Known Limitations

1. **Chrome headless closing immediately** — `input()` call in `download.py:105` may prevent PDF capture before Chrome exits. Consider polling for file instead.
2. **History/Bookmarks incomplete** — pages exist but functionality minimal.
3. **Session expiration** — Flask sessions are ephemeral (reset on app restart). For persistence, use Flask-Login or implement DB-backed sessions.
4. **No password reset** — admin password hardcoded in config.yaml. Change in config and restart app to update.

---

## Branch & PR Strategy

- **Current branch:** `feature/journal-club-downloader`
- **Base branch:** `main`
- **Commit message style:** `feat:`, `fix:`, `refactor:` prefixes
- **Before merge:** Test admin login, test DOI resolution in History, test Resend email

