# journal_club/toc_pdf_downloader.py
"""
Download and manage AJOG Table of Contents PDFs.
Automatically downloads TOC PDFs for each issue and stores them with metadata.
"""
import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

from journal_club.browser import launch_browser
from journal_club.config import Config


# Directory to store TOC PDFs
_TOC_PDF_DIR = Path(__file__).parent.parent / "toc_pdfs"


def get_toc_pdf_dir() -> Path:
    """Get or create the TOC PDF storage directory."""
    _TOC_PDF_DIR.mkdir(parents=True, exist_ok=True)
    return _TOC_PDF_DIR


def extract_issue_metadata(html_content: str) -> dict:
    """
    Extract volume, issue, month, year from AJOG current issue page.

    Returns dict with keys: volume, issue, month, year, issue_label
    """
    metadata = {
        "volume": None,
        "issue": None,
        "month": None,
        "year": None,
        "issue_label": None,
    }

    # Look for "Volume 234, Issue 4" or similar
    vol_match = re.search(r'Volume\s+(\d+)', html_content)
    if vol_match:
        metadata["volume"] = vol_match.group(1)

    issue_match = re.search(r'Issue\s+(\d+)', html_content)
    if issue_match:
        metadata["issue"] = issue_match.group(1)

    # Look for month/year like "APRIL 2026"
    month_match = re.search(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{4})', html_content, re.IGNORECASE)
    if month_match:
        month_name = month_match.group(1).lower()
        metadata["month"] = month_name
        metadata["year"] = month_match.group(2)
        metadata["issue_label"] = f"Vol {metadata['volume']} Issue {metadata['issue']} {month_name.capitalize()} {metadata['year']}"

    return metadata


def construct_pdf_filename(metadata: dict) -> str:
    """
    Construct a standardized filename for the TOC PDF.
    Format: toc_ajog_v234_i4_2026_04.pdf (volume, issue, year, month)
    """
    vol = metadata.get("volume", "unknown")
    issue = metadata.get("issue", "unknown")
    year = metadata.get("year", "unknown")

    # Month to number mapping
    month_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12"
    }
    month_num = month_map.get(metadata.get("month", "").lower(), "00")

    return f"toc_ajog_v{vol}_i{issue}_{year}_{month_num}.pdf"


def find_existing_pdf(volume: str, issue: str) -> Optional[str]:
    """
    Check if we already have a PDF for this volume/issue.
    Returns path if found, None otherwise.
    """
    pdf_dir = get_toc_pdf_dir()
    pattern = f"toc_ajog_v{volume}_i{issue}_*.pdf"

    matching_files = list(pdf_dir.glob(pattern))
    if matching_files:
        return str(matching_files[0])

    return None


def download_ajog_toc_pdf(cfg: Config, metadata: Optional[dict] = None, timeout: int = 10000) -> Optional[str]:
    """
    Download the current AJOG TOC PDF.

    Returns the path to the downloaded PDF, or None if download failed.
    Falls back to returning None, which triggers PubMed fallback in scraper.

    Note: Cloudflare blocks direct PDF access even from browsers. The HTML page
    content is extracted and returned to the scraper for HTML-based parsing as a fallback.
    """
    pdf_dir = get_toc_pdf_dir()

    try:
        with launch_browser(cfg.chrome_profile, cfg.chrome_path) as (p, browser, context, page):
            print("[AJOG PDF] Navigating to ajog.org/current...")
            page.goto("https://www.ajog.org/current", wait_until="networkidle", timeout=20_000)

            # Extract and return the page content for HTML scraping
            # (Cloudflare blocks direct PDF access, so we use browser-loaded HTML instead)
            html_content = page.content()
            metadata = extract_issue_metadata(html_content)

            # Check if we already have this issue
            if metadata.get("volume") and metadata.get("issue"):
                existing = find_existing_pdf(metadata["volume"], metadata["issue"])
                if existing:
                    print(f"[AJOG PDF] Already have PDF for this issue: {existing}")
                    return existing

            # Save the HTML content to a special marker file so scraper can use it
            # This is a workaround for Cloudflare blocking direct PDF access
            print("[AJOG PDF] Saving page content for HTML parsing (Cloudflare blocks PDF URLs)...")
            html_file = pdf_dir / f"ajog_page_html_{metadata.get('volume', 'unknown')}_{metadata.get('issue', 'unknown')}.txt"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"[AJOG PDF] Saved page HTML to {html_file.name}")

            # Return special marker to indicate HTML content is available
            return f"html:{html_file}"

            # Try to get the PDF URL from the href attribute
            pdf_href = pdf_links[0].get_attribute("href")
            if not pdf_href:
                print("[AJOG PDF] PDF link has no href")
                return None

            # Make absolute URL if needed
            if pdf_href.startswith('/'):
                pdf_url = "https://www.ajog.org" + pdf_href
            else:
                pdf_url = pdf_href

            print(f"[AJOG PDF] PDF URL: {pdf_url}")
            print("[AJOG PDF] Downloading PDF...")

            # Try multiple strategies to download the PDF
            download = None

            # Strategy 1: Use click on the PDF link with download interception
            try:
                print("[AJOG PDF] Strategy 1: Clicking PDF link with download handler...")
                with page.expect_download(timeout=30000) as download_info:
                    pdf_links[0].click(force=True, timeout=10000)
                download = download_info.value
                print(f"[AJOG PDF] ✓ Download via click succeeded")
            except Exception as e:
                print(f"[AJOG PDF] ✗ Click method failed: {e}")

            # Strategy 2: Use right-click context menu "Save link as"
            if not download:
                try:
                    print("[AJOG PDF] Strategy 2: Right-click context menu...")
                    with page.expect_download(timeout=30000) as download_info:
                        pdf_links[0].click(button="right", force=True, timeout=5000)
                        # Try clicking "Save as" or equivalent in context menu
                        page.wait_for_timeout(500)
                        # This approach is unreliable, skip if we get here
                    download = download_info.value
                    print(f"[AJOG PDF] ✓ Download via context menu succeeded")
                except Exception as e:
                    print(f"[AJOG PDF] ✗ Context menu method failed: {e}")

            # Strategy 3: Fetch PDF directly using page.request with proper headers
            if not download:
                try:
                    print("[AJOG PDF] Strategy 3: Direct fetch with request API...")
                    # Use the browser's request context to maintain cookies/session
                    response = page.request.get(pdf_url, timeout=30000)
                    if response.status == 200:
                        pdf_data = response.body()
                        filename = construct_pdf_filename(metadata)
                        pdf_path = pdf_dir / filename

                        with open(pdf_path, "wb") as f:
                            f.write(pdf_data)

                        file_size = pdf_path.stat().st_size
                        print(f"[AJOG PDF] ✓ Downloaded successfully via request API: {pdf_path.name} ({file_size:,} bytes)")
                        return str(pdf_path)
                    else:
                        print(f"[AJOG PDF] ✗ Request returned status {response.status}: {response.text()[:200]}")
                except Exception as e:
                    print(f"[AJOG PDF] ✗ Direct fetch failed: {e}")

            if not download:
                print("[AJOG PDF] ✗ All download strategies failed")
                return None

            # Save downloaded file
            filename = construct_pdf_filename(metadata)
            pdf_path = pdf_dir / filename

            download.save_as(str(pdf_path))

            file_size = pdf_path.stat().st_size
            print(f"[AJOG PDF] Downloaded successfully: {pdf_path.name} ({file_size:,} bytes)")

            return str(pdf_path)

    except Exception as e:
        print(f"[AJOG PDF] Download failed: {e}")
        return None


if __name__ == "__main__":
    from journal_club.config import load_config

    cfg = load_config("config.yaml")

    # Try to download
    pdf_path = download_ajog_toc_pdf(cfg)
    if pdf_path:
        print(f"\nSuccessfully downloaded to: {pdf_path}")
    else:
        print("\nFailed to download PDF")
