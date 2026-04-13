"""
Simple HTTP PDF downloader.
Downloads a PDF from a direct URL without requiring a browser session.
"""
import httpx
import os
import logging

log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def download_pdf_http(
    url: str,
    out_path: str,
    cookies: dict | None = None,
    headers: dict | None = None,
) -> bool:
    """Download a PDF via HTTP. Returns True if PDF saved successfully."""
    req_headers = {"User-Agent": _USER_AGENT}
    if headers:
        req_headers.update(headers)

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=30,
            headers=req_headers,
        ) as client:
            if cookies:
                client.cookies.update(cookies)

            print(f"[HTTP] GET {url[:80]}")
            resp = client.get(url)

            if resp.status_code != 200:
                print(f"[HTTP] Non-200 status: {resp.status_code}")
                return False

            content_type = resp.headers.get("content-type", "").lower()
            content = resp.content

            # Validate it's actually a PDF
            is_pdf_content_type = "pdf" in content_type or "octet-stream" in content_type
            is_pdf_magic = content[:4] == b"%PDF"

            if not (is_pdf_content_type or is_pdf_magic):
                print(
                    f"[HTTP] Response does not appear to be a PDF "
                    f"(content-type: {content_type}, "
                    f"first 4 bytes: {content[:4]!r})"
                )
                return False

            # Write to disk
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(content)

            print(f"[HTTP] Saved {len(content):,} bytes to {out_path}")
            return True

    except httpx.TimeoutException:
        print(f"[HTTP] Timeout downloading {url[:80]}")
        return False
    except Exception as e:
        print(f"[HTTP] Error downloading {url[:80]}: {e}")
        return False
