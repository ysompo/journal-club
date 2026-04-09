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
    Returns an empty TocResult on HTTP errors rather than raising,
    so a single failed journal doesn't break a batch refresh.
    """
    try:
        r = requests.get(toc_url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
    except requests.HTTPError as e:
        print(f"   [TOC] HTTP {e.response.status_code} for {toc_url} — skipping")
        return TocResult(issue_label="")
    except requests.RequestException as e:
        print(f"   [TOC] Network error for {toc_url}: {e} — skipping")
        return TocResult(issue_label="")
    soup = BeautifulSoup(r.text, "html.parser")

    parsers = {
        "nejm":             _parse_nejm,
        "jama":             _parse_jama,
        "lancet":           _parse_lancet,
        "nature":           _parse_nature,
        "bmj":              _parse_bmj,
        "acpjournals":      _parse_acpjournals,
        "ahajournals":      _parse_ahajournals,
        "jacc":             _parse_jacc,
        "chest":            _parse_generic,
        "asco":             _parse_generic,
        "blood":            _parse_generic,
        "diabetesjournals": _parse_generic,
    }

    parser = parsers.get(publisher, _parse_generic)
    return parser(soup, toc_url)


# ── NEJM ──────────────────────────────────────────────────────────────────────

def _parse_nejm(soup: BeautifulSoup, base_url: str) -> TocResult:
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
        articles.append({
            "url": url, "title": title, "authors": authors,
            "article_type": "", "doi": None, "abstract": "",
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
        articles.append({
            "url": url, "title": title, "authors": authors,
            "article_type": "", "doi": None, "abstract": "",
        })

    return TocResult(issue_label=_clean_label(issue_label), articles=articles)


# ── JACC ──────────────────────────────────────────────────────────────────────

def _parse_jacc(soup: BeautifulSoup, base_url: str) -> TocResult:
    return _parse_generic(soup, base_url, host="https://www.jacc.org")


# ── Generic fallback ──────────────────────────────────────────────────────────

def _parse_generic(soup: BeautifulSoup, base_url: str, host: str | None = None) -> TocResult:
    """Best-effort parser for unknown publishers."""
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
    seen: set[str] = set()
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
    """Collapse whitespace."""
    return re.sub(r"\s+", " ", s).strip()
