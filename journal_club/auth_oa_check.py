# journal_club/auth_oa_check.py
"""
Open-access check: try to find + fetch a PDF link directly in the DOM.
Must be called BEFORE any auth flow.
Returns True if PDF was captured, False otherwise.
"""
import time
from playwright.sync_api import Page, BrowserContext

from journal_club.pdf_capture import wait_for_pdf

_PDF_LINK_JS = """
() => {
    const host = window.location.hostname;
    // Only consider links on the same top-level domain (last two segments)
    const tld = host.split('.').slice(-2).join('.');
    const links = Array.from(document.querySelectorAll('a[href]'));
    const pdf = links.find(a => {
        try { if (!new URL(a.href).hostname.endsWith(tld)) return false; } catch(e) { return false; }
        // Exclude links inside reference/bibliography sections
        if (a.closest('[class*="reference"], [class*="Reference"], .References, [id*="ref"],\
 .bib, [class*="bib"], [class*="citation"], ol.references, ul.references')) return false;
        return (a.href.endsWith('.pdf') || a.href.includes('/pdf') || a.href.includes('pdf=1')) &&
               (a.innerText || a.textContent || '').toLowerCase().includes('pdf');
    });
    return pdf ? pdf.href : null;
}
"""

def check_open_access(page: Page, context: BrowserContext,
                      captured: list, timeout_s: int = 15) -> tuple[bool, str | None]:
    """
    Navigate to article_url (already loaded on page), look for a direct PDF link.
    If found, open it in a new tab and wait for PDF capture.
    Returns (True, pdf_url) if PDF captured, (False, pdf_url) if link found but blocked,
    (False, None) if no PDF link found.
    """
    print("\n[OA Check] Scanning DOM for direct PDF link...")

    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    pdf_href: str | None = None
    try:
        pdf_href = page.evaluate(_PDF_LINK_JS)
    except Exception as e:
        print(f"   [OA Check] JS eval error: {e}")

    if not pdf_href:
        print("   [OA Check] No direct PDF link found.")
        return False, None

    print(f"   [OA Check] Found PDF link: {pdf_href[:80]}")

    # Open in a new tab — lets Chrome handle the Cloudflare JS challenge
    # ("Preparing your download") and any redirect chain before delivering the PDF.
    # The on_download hook in pdf_capture.py will fire once the file arrives.
    pdf_tab = None
    try:
        pdf_tab = context.new_page()
        pdf_tab.goto(pdf_href, wait_until="commit", timeout=30_000)
        print(f"   [OA Check] Tab landed on: {pdf_tab.url[:80]}")
    except Exception as e:
        print(f"   [OA Check] Navigation error: {e}")

    if not captured:
        wait_for_pdf(captured, timeout_s=timeout_s)

    if captured:
        print("   [OA Check] Open access confirmed — PDF captured!")
        if pdf_tab:
            try:
                pdf_tab.close()
            except Exception:
                pass
        return True, pdf_href

    if pdf_tab:
        try:
            pdf_tab.close()
        except Exception:
            pass

    print("   [OA Check] PDF not accessible without auth.")
    return False, pdf_href
