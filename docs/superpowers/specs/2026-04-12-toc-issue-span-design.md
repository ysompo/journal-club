# TOC Issue Span — Design Spec

**Date:** 2026-04-12  
**Branch:** `feature/journal-club-downloader`

---

## Problem

The TOC scraper currently fetches only the **current (latest) issue** of each journal. Users sometimes want to browse articles from recent back issues — up to a year's worth — without manually triggering individual scrapes.

---

## Solution

Add a per-journal **"issues to fetch"** setting (default: 1). When N > 1, the scraper fetches the current issue via HTML (existing behavior) and appends back-issue articles via PubMed date-based query. A small button on each journal row shows the current span and opens a modal to change it.

---

## Design

### 1. Data Model

Add one column to the `journals` table:

```sql
ALTER TABLE journals ADD COLUMN issues_to_fetch INTEGER DEFAULT 1;
```

No changes to `toc_articles` — it already stores `issue_label`, so articles from different issues coexist naturally.

New storage function:
```python
def set_journal_issue_span(journal_id: int, n: int) -> None
```

`get_journals()` returns the new column (already returns full rows).

---

### 2. Catalog Changes

Add `days_per_issue: int` field to `CatalogEntry` in `journals_catalog.py`:

| Frequency | Value | Journals |
|-----------|-------|---------|
| Weekly    | `7`   | NEJM, JAMA, Lancet, BMJ, Circulation, NEJM Evidence |
| Monthly   | `30`  | Nature Medicine, Cell, and other monthly journals |

For custom-added journals (not in catalog): default `days_per_issue = 7`.

---

### 3. Scraper Changes (`toc_scraper.py`)

`scrape()` gets a new optional parameter:

```python
def scrape(publisher: str, toc_url: str, issn: str | None = None, issues_to_fetch: int = 1) -> TocResult
```

**Behavior:**

- `issues_to_fetch == 1` (default): existing behavior unchanged — HTML scrape, PubMed fallback if 0 results.
- `issues_to_fetch > 1`:
  1. Run HTML scrape for the current issue (N=1 behavior) → `current_articles`
  2. Call `scrape_via_pubmed()` with `reldate = issues_to_fetch * days_per_issue` → `back_articles`
  3. Merge: deduplicate by DOI (prefer HTML article over PubMed duplicate if DOI matches)
  4. Return merged `TocResult` with articles tagged by their `issue_label`

If ISSN is unavailable (can't use PubMed), fall back to HTML-only with a logged warning.

---

### 4. App Layer (`app.py`)

In `_refresh_journal()`, read `issues_to_fetch` from the journal row and pass it to `scrape()`:

```python
result = scrape(publisher, journal["toc_url"], issn=journal.get("issn"), issues_to_fetch=journal.get("issues_to_fetch", 1))
```

New route:
```
POST /journals/<id>/settings
  Body: {"issues_to_fetch": N}
  Auth: none (same as other journal routes)
  Returns: {"status": "saved"}
```

---

### 5. UI (`templates/journals.html`)

**Journal list row:**  
Each row gets a small pill button showing the current span:

```
[● NEJM]  [1 issue ▾]   [↻]  [✕]
```

- Button label: `"1 issue"` (N=1) or `"last N issues"` (N>1)
- Clicking the button opens a modal

**Modal:**
- Title: journal name
- Input: number field, label "Fetch last N issues", min=1, max=52, value=current N
- Save button → `POST /journals/<id>/settings`
- On save: update button label in-place, close modal

---

## Out of Scope

- Per-publisher HTML back-issue navigation (too fragile at N=52)
- Global span setting (per-journal is more useful)
- Automatic span increase on "no new issue" detection

---

## Verification

1. **Unit tests:** Add `tests/test_toc_scraper.py` cases for `issues_to_fetch > 1` — mock PubMed response, verify dedup by DOI works.
2. **Manual — default behavior:** Refresh a journal with N=1, confirm only current issue articles appear (no regression).
3. **Manual — back issues:** Set N=4 on NEJM (has ISSN), trigger refresh, confirm articles from ~4 weeks appear with correct `issue_label` values.
4. **Manual — no ISSN:** Set N=3 on a custom journal with no ISSN, confirm graceful fallback to HTML-only with no crash.
5. **Manual — UI:** Open journal modal, change N, save, confirm button label updates and persists after page reload.
