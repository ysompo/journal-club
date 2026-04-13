"""
Unpaywall API client.
Queries the Unpaywall API to find open-access PDF URLs for a given DOI.
"""
import httpx
import logging

log = logging.getLogger(__name__)

_UNPAYWALL_BASE = "https://api.unpaywall.org/v2"


def query_unpaywall(doi: str, email: str) -> dict | None:
    """Query Unpaywall API for open-access PDF URL and abstract.

    Returns {"pdf_url": str, "abstract": str} or None on failure.
    """
    url = f"{_UNPAYWALL_BASE}/{doi}?email={email}"
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        best_oa = data.get("best_oa_location")
        if not best_oa:
            print(f"[Unpaywall] No OA location for DOI {doi}")
            return None

        pdf_url = best_oa.get("url_for_pdf")
        if not pdf_url:
            print(f"[Unpaywall] OA location found but no PDF URL for DOI {doi}")
            return None

        abstract = data.get("abstract", "")
        print(f"[Unpaywall] Found OA PDF for DOI {doi}: {pdf_url[:80]}")
        return {"pdf_url": pdf_url, "abstract": abstract}

    except httpx.TimeoutException:
        print(f"[Unpaywall] Timeout querying DOI {doi}")
        return None
    except httpx.HTTPStatusError as e:
        print(f"[Unpaywall] HTTP {e.response.status_code} for DOI {doi}")
        return None
    except Exception as e:
        print(f"[Unpaywall] Error querying DOI {doi}: {e}")
        return None
