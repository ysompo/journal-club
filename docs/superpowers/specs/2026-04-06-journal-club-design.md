# Journal Club — Product Design Spec
**Date:** 2026-04-06
**Status:** Under review

---

## Context

A researcher needs a personal, self-hosted tool to follow academic medical journals, automatically fetch new articles (including full-text PDFs using their institutional credentials), read and annotate papers, and manage their reading list — all from a single app that works on desktop, tablet, and phone.

The motivation: journal websites are fragmented and noisy. The researcher wants one curated feed of only the articles that matter to them (filtered by journal + keyword), with the ability to annotate and organize without leaving the app, and to email themselves PDFs for offline reading.

---

## What We're Building

**Journal Club** — a cloud-hosted multi-user academic reading companion, deployed on Labor-AI.org.

- Accessible at `app.labor-ai.org` (or `journals.labor-ai.org`) — any browser, any device, anywhere
- Multi-user: each researcher creates an account, has their own journal list, credentials, annotations, and reading list
- Installable as a **PWA** on tablet and mobile (Add to Home Screen)
- **Optional:** Electron desktop app for users who want everything stored locally (future v2 consideration)

### Deployment Stack
| Layer | Service | Cost |
|-------|---------|------|
| Frontend (Next.js) | Vercel | Free tier |
| Backend (Python FastAPI + scraper) | Railway | ~$5–10/mo |
| Database (PostgreSQL) | Railway | ~$5/mo |
| PDF Storage | Cloudflare R2 | Free up to 10 GB, then $0.015/GB |
| Domain | Namecheap → Vercel/Railway | Already owned |

---

## Architecture

```
  Browser / PWA (any device, anywhere)
        │  https://app.labor-ai.org
        ▼
┌─────────────────────────────────────────────────────────────┐
│  Vercel                                                     │
│  Next.js 14 (App Router, PWA)                               │
│  - UI, auth pages, PDF viewer                               │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API calls
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Railway                                                    │
│  FastAPI (Python)                                           │
│  - PubMed sync scheduler (APScheduler, per-user)            │
│  - PDF download scraper (Playwright, per-journal module)    │
│  - Auth API, article API, annotation API                    │
│                      │                                      │
│  PostgreSQL (Railway) │  Cloudflare R2                      │
│  users, journals,     │  downloaded PDFs                    │
│  articles, bookmarks, │  (per-user, private URLs)           │
│  annotations          │                                     │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
          PubMed API (NCBI E-utilities) — free, public
```

### Two-stage article pipeline

| Stage | Source | What it fetches |
|-------|--------|-----------------|
| **Metadata** | PubMed API (NCBI E-utilities) | Title, authors, abstract, DOI, pub date, journal, article type — free, no credentials needed |
| **Full text** | Journal website scraper (Playwright) | Full-text PDF only — uses user-provided credentials per journal |

PubMed handles all discovery and metadata reliably. The scraper is a targeted, credential-based PDF downloader — not a general crawler.

### Components

| Component | Stack | Role |
|-----------|-------|------|
| `frontend` | Next.js 14 (App Router), Tailwind CSS, PWA | UI on Vercel |
| `api` | FastAPI (Python) on Railway | All backend logic, auth, scheduling |
| `scraper` | Playwright (inside FastAPI service) | Per-journal PDF download modules |
| `db` | PostgreSQL on Railway | All structured data, per-user |
| `storage` | Cloudflare R2 | PDF files, accessed via signed URLs |

---

## Design System

Uses the existing **"Editorial Authority"** design system from `stitch/academic_journal_modern/DESIGN.md`:
- **Colors:** Deep navy primary `#005977`, teal accent `#007398`
- **Typography:** Noto Serif (headlines) / Inter (body) / Work Sans (labels)
- **Style:** No-line rule, tonal surface layering, boxy/structured aesthetic, glassmorphism nav
- **Existing screens to reuse:** `journal_feed_tablet_landscape`, `search_discovery_tablet_landscape`, `expanded_article_abstract`

---

## Features

### 1. Discipline & Journal Setup (Onboarding)

On first launch, the user selects their **primary discipline**. This pre-populates their journal list with the curated set for that discipline. They can add or remove journals freely after setup.

#### General / Interdisciplinary (always included by default)
| Journal | PubMed ISSN | Cadence |
|---------|------------|---------|
| New England Journal of Medicine | 0028-4793 | Weekly |
| JAMA | 0098-7484 | Weekly |
| The BMJ | 0959-8138 | Weekly |
| The Lancet | 0140-6736 | Weekly |
| Nature Medicine | 1078-8956 | Monthly |

#### Discipline: Obstetrics & Gynecology (starter set)
| Journal | PubMed ISSN | Cadence |
|---------|------------|---------|
| American Journal of Obstetrics & Gynecology (AJOG) | 0002-9378 | Monthly |
| BJOG: An International Journal of Obstetrics & Gynaecology | 1470-0328 | Monthly |
| Obstetrics & Gynecology (Green Journal) | 0029-7844 | Monthly |
| Fertility and Sterility | 0015-0282 | Monthly |
| Human Reproduction | 0268-1161 | Monthly |
| Gynecologic Oncology | 0090-8258 | Monthly |
| AJOG MFM (MFM subspecialty) | 2589-9333 | Bi-monthly |
| Journal of Maternal-Fetal & Neonatal Medicine | 1476-7058 | Monthly |
| Ultrasound in Obstetrics & Gynecology | 0960-7692 | Monthly |
| Prenatal Diagnosis | 0197-3851 | Monthly |
| Journal of Minimally Invasive Gynecology | 1553-4650 | Bi-monthly |
| Gynecological Endocrinology | 0951-3590 | Monthly |

#### Future disciplines (extensible — same pattern)
- Cardiology, Oncology, Pediatrics, Internal Medicine, Surgery, Neurology, etc.
- Each discipline has its own curated list of 10–12 top journals

#### Free-text journal search
- Search box in journal settings searches PubMed's journal database (NLM Catalog API)
- User can find and add any journal by name, keyword, or ISSN
- Added journals use a default weekly sync cadence (user-adjustable)

---

### 2. Per-Journal Configuration

For each followed journal the user configures:
- **Keywords** (optional) — comma-separated; PubMed query is constructed to filter by these terms within the journal. Applied at the PubMed query level (not post-fetch), so only matching articles are ever stored.
- **Credentials** — username/password for the journal's website, stored encrypted (Fernet) in SQLite. Used only by the PDF downloader, not the metadata sync.
- **Sync cadence** — pre-filled from registry; user can override.

---

### 3. Article Metadata Sync (PubMed)

The sync service queries PubMed's E-utilities API for each followed journal on its cadence:

```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
  ?db=pubmed
  &term="{journal_name}"[Journal]+AND+{keywords}
  &reldate=<days_since_last_sync>
  &retmax=200
```

- Fetches: title, authors, abstract, DOI, pub date, article type, PubMed ID
- Stores metadata in SQLite immediately (no PDF needed to appear in feed)
- Queues PDF download job for matching articles if credentials are configured
- No API key needed for low volume; NCBI API key added in Settings for higher rate limits

---

### 4. Article Feed (Home)

- Chronological feed of synced articles from all followed journals
- Card shows: journal name, article type chip, title, authors, date, abstract snippet, PDF status badge
- Filter bar: by journal, date range, article type
- "Unread / All" toggle
- Maps to existing `journal_feed_tablet_landscape` screen

---

### 5. Search & Discovery

- Full-text search across local article database (title + abstract)
- **"Search PubMed"** button — runs a live PubMed query and shows results not yet in the local database, with option to add individual articles
- Filter facets: journal, year, article type, PDF available
- Maps to existing `search_discovery_tablet_landscape` screen

---

### 6. Article Detail / Reading View

- Full abstract displayed
- Embedded PDF reader (pdf.js) when PDF has been downloaded
- "Request PDF" button if credentials are configured but PDF not yet fetched
- Annotation toolbar overlaid on PDF reader
- Maps to existing `expanded_article_abstract` screen

---

### 7. Highlights & Notes

- In-PDF: select text → choose highlight color → optionally attach a typed note
- Notes panel alongside PDF showing all highlights + notes for the article
- Annotations stored in SQLite with PDF page + coordinate position data (JSON)

---

### 8. Bookmarks & Reading List

- Star/bookmark any article from feed or detail view
- Reading status: `unread` → `in_progress` → `done`
- Dedicated `/reading-list` screen

---

### 9. Email PDF to Self

- One-click button on article detail view
- Attaches full-text PDF; falls back to abstract text if no PDF available
- User configures SMTP once in Settings (Gmail, Outlook, custom SMTP)

---

### 10. PDF Download Scraper

- Runs per-journal, triggered after PubMed sync finds matching articles
- Each journal site has its own Python module with a recorded auth + navigation sequence
- Playwright drives the browser headlessly
- **User demonstrates the exact steps** needed to reach and download a PDF on each journal site — these steps are encoded into the module for that journal
- Downloaded PDFs stored in the local Docker volume; path recorded in `articles.pdf_path`

---

## Data Model (SQLite)

```
users           id, email, password_hash, discipline, created_at,
                smtp_host, smtp_user, smtp_pass_encrypted, email_to,
                ncbi_api_key, onboarding_complete

user_journals   id, user_id, journal_id, keywords, credentials_encrypted,
                schedule_cadence, last_synced, is_active

journals        id, name, issn, url, discipline, default_cadence
                (shared table — journal definitions, not per-user config)

articles        id, journal_id, pubmed_id, title, authors, abstract,
                doi, pub_date, article_type
                (shared — article metadata is the same for all users)

user_articles   id, user_id, article_id, pdf_r2_key, pdf_status
                (none | queued | downloading | available | failed), is_new

bookmarks       id, user_id, article_id, status (unread/in_progress/done),
                created_at

annotations     id, user_id, article_id, page,
                position_data (JSON: pdf.js coords),
                color, note_text, created_at
```

---

## UI Screens

| Screen | Route | Notes |
|--------|-------|-------|
| Home / Feed | `/` | From `journal_feed_tablet_landscape` |
| Search | `/search` | From `search_discovery_tablet_landscape` |
| Article Detail | `/article/[id]` | From `expanded_article_abstract` |
| Reading List | `/reading-list` | New — same card design |
| Journal Settings | `/settings/journals` | Add/edit/remove journals; credentials, keywords, cadence per journal |
| App Settings | `/settings` | SMTP, NCBI API key, discipline, scraper status |
| Onboarding | `/onboarding` | Discipline picker + journal list confirmation, shown once on first launch |

---

## Distribution & Access

- **Any device:** Open `https://app.labor-ai.org` in any browser — desktop, tablet, phone. No install required.
- **PWA install:** On tablet/phone, tap "Add to Home Screen" to install as an app icon. Works offline for cached content.
- **Sign up:** User creates an account with email + password. Email verification on sign-up.
- No downloads, no setup, no Docker, no terminal — just a URL.

---

## Out of Scope (v1)

- Shared reading lists or collaborative annotation between users
- Citation manager export (Zotero, Mendeley)
- Social features (comments, sharing)
- Native iOS/Android apps (PWA covers tablet/phone)
- Electron desktop / local-only version (structure allows this later)
- Disciplines other than OB/GYN + General (schema supports adding more)
