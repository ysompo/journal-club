# journal_club/resolver.py
"""
Resolve any of these inputs to a publisher article URL + article metadata:
  - PMID              (bare integer, e.g.  39794646)
  - PubMed URL        (https://pubmed.ncbi.nlm.nih.gov/39794646/)
  - DOI               (10.1056/NEJMoa2504068  or  doi:10.1056/...)
  - Article URL       (direct journal URL — returned as-is)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

# ── NCBI E-utils base ─────────────────────────────────────────────────────────
_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_HEADERS = {"User-Agent": "JournalClubDownloader/1.0 (mailto:research@example.com)"}
_TIMEOUT = 15


@dataclass
class ArticleMetadata:
    url: str                        # resolved publisher article URL
    pmid: str | None = None
    doi:  str | None = None
    title: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    pub_date: str = ""
    abstract: str = ""


# ── Input classification ──────────────────────────────────────────────────────

_PMID_RE  = re.compile(r"^\d{6,9}$")
_DOI_RE   = re.compile(r"^(?:doi:)?10\.\d{4,9}/\S+$", re.IGNORECASE)
_PUBMED_RE = re.compile(
    r"(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/(\d+)", re.IGNORECASE
)


def _classify(s: str) -> tuple[str, str]:
    """
    Return (kind, value) where kind is one of:
      'pmid', 'doi', 'url'
    and value is the cleaned identifier.
    """
    s = s.strip()
    m = _PUBMED_RE.search(s)
    if m:
        return "pmid", m.group(1)
    if _PMID_RE.match(s):
        return "pmid", s
    if _DOI_RE.match(s):
        doi = re.sub(r"^doi:", "", s, flags=re.IGNORECASE)
        return "doi", doi
    return "url", s


# ── NCBI helpers ─────────────────────────────────────────────────────────────

def _fetch_by_pmid(pmid: str) -> ArticleMetadata:
    """Call NCBI esummary + efetch and return a populated ArticleMetadata."""
    meta = ArticleMetadata(url="", pmid=pmid)

    # esummary — title, journal, pub_date, doi, authors
    try:
        r = requests.get(
            f"{_EUTILS}/esummary.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "json"},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        doc = r.json().get("result", {}).get(pmid, {})
        meta.title   = doc.get("title", "").rstrip(".")
        meta.journal = doc.get("source", "")
        meta.pub_date = doc.get("pubdate", "")

        # Authors
        meta.authors = [
            a["name"] for a in doc.get("authors", []) if a.get("authtype") == "Author"
        ]

        # DOI from articleids list
        for aid in doc.get("articleids", []):
            if aid.get("idtype") == "doi":
                meta.doi = aid["value"]
                break
    except Exception as e:
        print(f"   [Resolver] esummary error for PMID {pmid}: {e}")

    # efetch — abstract text (XML)
    try:
        r = requests.get(
            f"{_EUTILS}/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "xml", "rettype": "abstract"},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        parts = []
        for node in root.iter("AbstractText"):
            label = node.get("Label")
            text  = (node.text or "").strip()
            if label:
                parts.append(f"{label}: {text}")
            elif text:
                parts.append(text)
        meta.abstract = " ".join(parts)
    except Exception as e:
        print(f"   [Resolver] efetch error for PMID {pmid}: {e}")

    return meta


def _elsevier_resolve(doi: str) -> str:
    """
    Resolve an Elsevier DOI to the actual publisher article URL, bypassing
    linkinghub.elsevier.com (which intermittently returns 504).

    Strategy:
    1. HEAD doi.org/{doi} — gets a 302 Location pointing at linkinghub.
    2. If linkinghub, try following it (fast when healthy).
    3. If linkinghub is slow/504, parse the Redirect= query param from its
       URL — that param *is* the real article URL (e.g. ajog.org/...).
    4. Falls back to doi.org URL on any error.
    """
    from urllib.parse import urlparse, parse_qs, unquote
    doi_url = f"https://doi.org/{doi}"
    _ua = {"User-Agent": "Mozilla/5.0 (compatible; JournalClubBot/1.0)"}
    try:
        r = requests.head(doi_url, allow_redirects=False, timeout=8, headers=_ua)
        loc = r.headers.get("Location", "")
        if not loc:
            return doi_url
        # doi.org jumped straight to the publisher — great
        if "linkinghub.elsevier.com" not in loc:
            print(f"   [Resolver] Elsevier direct redirect: {loc[:80]}")
            return loc
        # Try following linkinghub itself (healthy → 302 to journal page)
        try:
            r2 = requests.head(loc, allow_redirects=False, timeout=5, headers=_ua)
            loc2 = r2.headers.get("Location", "")
            if loc2 and r2.status_code in (301, 302, 303, 307, 308):
                print(f"   [Resolver] Elsevier via linkinghub: {loc2[:80]}")
                return loc2
        except Exception:
            pass
        # linkinghub is down/slow — extract Redirect= param from its URL
        qs = parse_qs(urlparse(loc).query)
        redirect = qs.get("Redirect", [""])[0]
        if redirect:
            target = unquote(redirect)
            print(f"   [Resolver] Elsevier Redirect param: {target[:80]}")
            return target
        # Last resort: PII-based ScienceDirect URL
        if "/pii/" in loc:
            pii = loc.split("/pii/")[-1].split("?")[0]
            return f"https://www.sciencedirect.com/science/article/pii/{pii}"
    except Exception as e:
        print(f"   [Resolver] Elsevier redirect error: {e}")
    return doi_url


def _doi_to_url(doi: str) -> str:
    """
    Return the best-guess publisher URL for a DOI.

    We resolve using well-known DOI prefixes so the Python process does not
    need to follow doi.org HTTP redirects (which are often intercepted by
    institutional network filters).  Unknown prefixes fall back to
    https://doi.org/{doi} — the browser will follow the redirect correctly.
    """
    if "10.1056" in doi:             # NEJM
        return f"https://www.nejm.org/doi/full/{doi}"
    if "10.1001" in doi:             # JAMA Network
        return f"https://jamanetwork.com/journals/jama/fullarticle/{doi}"
    if "10.1136" in doi:             # BMJ
        return f"https://www.bmj.com/content/{doi.split('/', 1)[-1]}"
    if "10.1093" in doi:             # OUP (academic.oup.com)
        return f"https://doi.org/{doi}"
    if "10.1016" in doi or "10.1053" in doi:   # Elsevier / ScienceDirect
        # Don't call _elsevier_resolve here — it makes 2-3 HTTP requests per DOI
        # which causes timeouts when scraping 40+ articles.  The browser follows
        # doi.org redirects fine; _elsevier_resolve is only for the download flow.
        return f"https://doi.org/{doi}"
    if "10.1038" in doi:             # Nature
        return f"https://www.nature.com/articles/{doi.split('/')[-1]}"
    if "10.1007" in doi:             # Springer
        return f"https://link.springer.com/article/{doi}"
    if "10.1111" in doi or "10.1002" in doi:   # Wiley
        return f"https://onlinelibrary.wiley.com/doi/{doi}"
    # Unknown prefix: return doi.org URL and let the browser resolve it
    return f"https://doi.org/{doi}"


# ── Public API ────────────────────────────────────────────────────────────────

def resolve(input_str: str) -> ArticleMetadata:
    """
    Accept a PMID, PubMed URL, DOI, or direct article URL.
    Return an ArticleMetadata whose .url is the canonical publisher page URL.
    """
    kind, value = _classify(input_str)

    if kind == "pmid":
        print(f"   [Resolver] PMID {value} -> fetching metadata from PubMed...")
        meta = _fetch_by_pmid(value)
        if meta.doi:
            print(f"   [Resolver] DOI {meta.doi} -> resolving to publisher URL...")
            meta.url = _doi_to_url(meta.doi)
        else:
            print(f"   [Resolver] No DOI found for PMID {value} — cannot resolve to publisher URL")
            meta.url = f"https://pubmed.ncbi.nlm.nih.gov/{value}/"
        print(f"   [Resolver] URL: {meta.url[:80]}")
        return meta

    if kind == "doi":
        print(f"   [Resolver] DOI {value} -> resolving to publisher URL...")
        url = _doi_to_url(value)
        # Try to look up metadata via PubMed search by DOI
        meta = _search_pubmed_by_doi(value)
        meta.doi = value
        meta.url = url
        print(f"   [Resolver] URL: {meta.url[:80]}")
        return meta

    # kind == "url" — direct article URL, no metadata lookup
    # Special case: doi.org URLs for Elsevier — follow redirect to bypass linkinghub
    if value.startswith("https://doi.org/") or value.startswith("http://doi.org/"):
        bare = value.split("doi.org/", 1)[-1]
        if "10.1016" in bare or "10.1053" in bare:
            resolved = _elsevier_resolve(bare)
            print(f"   [Resolver] Direct doi.org → {resolved[:80]}")
            return ArticleMetadata(url=resolved)
    print(f"   [Resolver] Direct URL: {value[:80]}")
    return ArticleMetadata(url=value)


def _search_pubmed_by_doi(doi: str) -> ArticleMetadata:
    """Try to find a PubMed record for a DOI and return its metadata."""
    try:
        r = requests.get(
            f"{_EUTILS}/esearch.fcgi",
            params={"db": "pubmed", "term": f"{doi}[doi]", "retmode": "json", "retmax": 1},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if ids:
            meta = _fetch_by_pmid(ids[0])
            meta.pmid = ids[0]
            return meta
    except Exception:
        pass
    return ArticleMetadata(url="")
