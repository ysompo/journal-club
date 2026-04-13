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
import xml.etree.ElementTree as ET
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
_PUBMED_HEADERS = {"User-Agent": "JournalClubDownloader/1.0 (mailto:research@example.com)"}
_TIMEOUT = 20
_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class TocResult:
    issue_label: str                          # e.g. "Vol 392 · Issue 19 · May 2025"
    articles: list[dict] = field(default_factory=list)
    # Each article dict has keys: url, title, authors (list), article_type, doi, abstract


def scrape_via_pubmed(issn: str, reldate: int = 0) -> TocResult:
    """
    Fetch articles for a journal by ISSN using PubMed eutils.
    When reldate > 0, fetches articles published within the last reldate days.
    Otherwise fetches the 40 most recent articles.
    """
    try:
        retmax = max(40, min(200, reldate // 7 * 15)) if reldate > 0 else 40
        params: dict = {
            "db": "pubmed",
            "term": f"{issn}[ISSN]",
            "sort": "pub date",
            "retmax": retmax,
            "retmode": "json",
        }
        if reldate > 0:
            params["reldate"] = reldate
            params["datetype"] = "edat"
        r = requests.get(
            f"{_EUTILS}/esearch.fcgi",
            params=params,
            headers=_PUBMED_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            print(f"   [TOC/PubMed] No results for ISSN {issn}")
            return TocResult(issue_label="")

        # Fetch summaries for all IDs in one call
        r2 = requests.get(
            f"{_EUTILS}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            headers=_PUBMED_HEADERS, timeout=_TIMEOUT,
        )
        r2.raise_for_status()
        result = r2.json().get("result", {})

        # Fetch abstracts via efetch XML in one batch call
        abstracts: dict[str, str] = {}
        try:
            r3 = requests.get(
                f"{_EUTILS}/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml", "rettype": "abstract"},
                headers=_PUBMED_HEADERS, timeout=_TIMEOUT,
            )
            r3.raise_for_status()
            root = ET.fromstring(r3.content)
            for article in root.iter("PubmedArticle"):
                pmid_el = article.find(".//MedlineCitation/PMID")
                if pmid_el is None:
                    continue
                pmid_val = pmid_el.text or ""
                parts = []
                for node in article.findall(".//Abstract/AbstractText"):
                    label = node.get("Label")
                    # Use itertext() to capture text inside child elements
                    # like <i>, <b>, <sub>, <sup> — node.text alone misses them
                    text = "".join(node.itertext()).strip()
                    if label and text:
                        parts.append(f"{label}: {text}")
                    elif text:
                        parts.append(text)
                abstracts[pmid_val] = " ".join(parts)
        except Exception as e:
            print(f"   [TOC/PubMed] Abstract fetch error: {e}")

        articles = []
        issue_label = ""

        for pmid in ids:
            doc = result.get(pmid, {})
            if not doc or doc.get("error"):
                continue

            title = doc.get("title", "").rstrip(".")
            if not title:
                continue

            pub_date = doc.get("pubdate", "")
            volume = doc.get("volume", "")
            issue = doc.get("issue", "")

            # Build issue label from the first article
            if not issue_label and (volume or issue):
                parts = []
                if volume:
                    parts.append(f"Vol {volume}")
                if issue:
                    parts.append(f"Issue {issue}")
                if pub_date:
                    parts.append(pub_date)
                issue_label = " · ".join(parts)

            # DOI
            doi = None
            for aid in doc.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = aid["value"]
                    break

            # Publisher URL from DOI
            from journal_club.resolver import _doi_to_url
            url = _doi_to_url(doi) if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            authors = [
                a["name"] for a in doc.get("authors", [])
                if a.get("authtype") == "Author"
            ]

            pub_types = doc.get("pubtype", [])
            # pubtype can be a list of strings OR a list of dicts with "value" key
            if pub_types and isinstance(pub_types[0], dict):
                article_type = pub_types[0].get("value", "")
            else:
                article_type = pub_types[0] if pub_types else ""

            articles.append({
                "url": url,
                "title": title,
                "authors": authors,
                "article_type": article_type,
                "doi": doi,
                "abstract": abstracts.get(pmid, ""),
                "issue_label": issue_label,
            })

        print(f"   [TOC/PubMed] ISSN {issn}: {len(articles)} articles, label='{issue_label}'")
        return TocResult(issue_label=issue_label, articles=articles)

    except Exception as e:
        print(f"   [TOC/PubMed] Error for ISSN {issn}: {e}")
        return TocResult(issue_label="")


def _enrich_abstracts(articles: list[dict], issn: str) -> None:
    """
    Fill in missing abstracts by querying PubMed for the journal's most recent
    articles and matching by DOI.  Called after HTML scraping, which never
    populates the abstract field.  Silently no-ops if PubMed returns nothing or
    if all articles already have abstracts.
    """
    dois_missing = {a["doi"] for a in articles if a.get("doi") and not a.get("abstract")}
    if not dois_missing:
        return
    try:
        pm = scrape_via_pubmed(issn)   # 40 most-recent articles with abstracts
        lookup = {
            a["doi"]: a["abstract"]
            for a in pm.articles
            if a.get("doi") and a.get("abstract")
        }
        n = 0
        for art in articles:
            if art.get("doi") and not art.get("abstract") and art["doi"] in lookup:
                art["abstract"] = lookup[art["doi"]]
                n += 1
        if n:
            print(f"   [TOC] Abstract enrichment: filled {n}/{len(articles)} via PubMed")
    except Exception as e:
        print(f"   [TOC] Abstract enrichment error: {e}")


def scrape(
    publisher: str,
    toc_url: str,
    issn: str | None = None,
    issues_to_fetch: int = 1,
    days_per_issue: int = 7,
) -> TocResult:
    """
    Fetch and parse a journal's TOC.

    issues_to_fetch=1 (default): HTML scrape of the current issue; falls back
    to PubMed if HTML yields 0 articles and an ISSN is available.

    issues_to_fetch>1 (hybrid): HTML scrape for the current issue + PubMed
    date-based query for back-issues (reldate = issues_to_fetch * days_per_issue),
    merged and deduplicated by DOI. Requires an ISSN; logs a warning and returns
    HTML-only if none is available.
    """
    reldate = issues_to_fetch * days_per_issue if issues_to_fetch > 1 else 0

    try:
        r = requests.get(toc_url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
    except requests.HTTPError as e:
        print(f"   [TOC] HTTP {e.response.status_code} for {toc_url} — trying PubMed fallback")
        if issn:
            return scrape_via_pubmed(issn, reldate=reldate)
        return TocResult(issue_label="")
    except requests.RequestException as e:
        print(f"   [TOC] Network error for {toc_url}: {e} — trying PubMed fallback")
        if issn:
            return scrape_via_pubmed(issn, reldate=reldate)
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
    result = parser(soup, toc_url)

    if issues_to_fetch == 1:
        # Default: PubMed fallback only when HTML yields nothing
        if not result.articles and issn:
            print(f"   [TOC] HTML parse returned 0 articles — trying PubMed fallback (ISSN {issn})")
            return scrape_via_pubmed(issn)
        # Enrich abstracts for HTML-scraped articles (parsers return empty abstract)
        if result.articles and issn:
            _enrich_abstracts(result.articles, issn)
        return result

    # Hybrid mode: append PubMed back-issues to HTML current issue
    if not issn:
        print(f"   [TOC] No ISSN for {toc_url} — cannot fetch back-issues, returning HTML-only")
        return result

    pubmed_result = scrape_via_pubmed(issn, reldate=reldate)

    if not result.articles:
        # HTML yielded nothing; use full PubMed result (already has abstracts)
        return pubmed_result

    # Use PubMed abstracts to enrich HTML articles (avoids a second API round-trip)
    pm_abstracts = {
        a["doi"]: a["abstract"]
        for a in pubmed_result.articles
        if a.get("doi") and a.get("abstract")
    }
    n_enriched = 0
    for art in result.articles:
        if art.get("doi") and not art.get("abstract") and art["doi"] in pm_abstracts:
            art["abstract"] = pm_abstracts[art["doi"]]
            n_enriched += 1
    if n_enriched:
        print(f"   [TOC] Hybrid: enriched {n_enriched} HTML abstracts from PubMed back-issue data")

    # Merge: HTML articles take precedence; skip PubMed duplicates by DOI or URL
    current_dois = {a["doi"] for a in result.articles if a.get("doi")}
    current_urls = {a["url"] for a in result.articles}
    for article in pubmed_result.articles:
        doi = article.get("doi")
        if doi and doi in current_dois:
            continue
        if article.get("url") in current_urls:
            continue
        result.articles.append(article)

    print(f"   [TOC] Hybrid merge: {len(result.articles)} total articles after back-issue append")
    return result


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
