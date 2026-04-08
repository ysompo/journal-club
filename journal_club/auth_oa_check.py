# journal_club/auth_oa_check.py
"""
Open-access check: try to find + navigate to a PDF link directly in the DOM.
Must be called BEFORE any auth flow.
Returns True if PDF was captured (open access confirmed).
"""
import time
from playwright.sync_api import Page, BrowserContext

from journal_club.pdf_capture import wait_for_pdf

_PDF_LINK_JS = """
() => {
    const links = Array.from(document.querySelectorAll('a[href]'));
    const pdf = links.find(a =>
        (a.href.endsWith('.pdf') || a.href.includes('/pdf') || a.href.includes('pdf=1')) &&
        (a.innerText || a.textContent || '').toLowerCase().includes('pdf')
    );
    return pdf ? pdf.href : null;
}
"""

def check_open_access(page: Page, context: BrowserContext,
                      captured: list, timeout_s: int = 15) -> bool:
    """
    Navigate to article_url (already loaded on page), look for a direct PDF link.
    If found, open it in a new tab and wait for PDF capture.
    Returns True if a PDF was captured.
    """
    print("\n[OA Check] Scanning DOM for direct PDF link...")

    pdf_href: str | None = None
    try:
        pdf_href = page.evaluate(_PDF_LINK_JS)
    except Exception as e:
        print(f"   [OA Check] JS eval error: {e}")

    if not pdf_href:
        print("   [OA Check] No direct PDF link found.")
        return False

    print(f"   [OA Check] Found PDF link: {pdf_href[:80]}")
    pdf_tab = None
    try:
        pdf_tab = context.new_page()
        pdf_tab.goto(pdf_href, wait_until="commit", timeout=20_000)
        time.sleep(8)
        print(f"   [OA Check] Tab landed on: {pdf_tab.url[:80]}")
    except Exception as e:
        print(f"   [OA Check] Navigation error: {e}")

    # Wait a bit longer for Chrome extension to deliver PDF bytes
    if not captured:
        wait_for_pdf(captured, timeout_s=timeout_s)

    if captured:
        print("   [OA Check] Open access confirmed — PDF captured!")
        return True

    # Close the tab so it doesn't interfere with the auth flow's PDF download
    if pdf_tab:
        try:
            pdf_tab.close()
        except Exception:
            pass

    print("   [OA Check] PDF not accessible without auth.")
    return False
