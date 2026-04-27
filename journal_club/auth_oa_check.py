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

def _try_wiley_epdf(page: Page, context: BrowserContext, captured: list, timeout_s: int = 15) -> bool:
    """Try Wiley's /doi/epdf/ pattern for open-access articles. Returns True if PDF captured.

    /doi/epdf/ is Wiley's in-browser reader (HTML wrapper around an iframe), not
    a PDF response. Waiting on it never captures anything. We instead navigate
    there, look for an iframe whose src ends with .pdf, and only then drive the
    PDF-capture code against that real PDF URL.
    """
    url = page.url
    if "wiley.com" not in url or "/doi/" not in url:
        return False

    # Convert /doi/10.xxxx to /doi/epdf/10.xxxx
    epdf_url = url.replace("/doi/", "/doi/epdf/")
    if epdf_url == url:
        return False

    print(f"   [OA Check] Trying Wiley epdf pattern: {epdf_url[:80]}")

    try:
        pdf_tab = context.new_page()
        pdf_tab.goto(epdf_url, wait_until="domcontentloaded", timeout=15_000)
        time.sleep(1)

        # Look for an embedded PDF iframe (Wiley's reader hosts the actual PDF
        # inside it). If found, navigate the tab to that direct URL.
        iframe_pdf = None
        try:
            iframe_pdf = pdf_tab.evaluate(
                "() => { const f = document.querySelector('iframe[src*=\".pdf\"], iframe[src*=\"/pdf\"]');"
                " return f ? f.src : null; }"
            )
        except Exception:
            pass

        if iframe_pdf:
            print(f"   [OA Check] Found Wiley PDF iframe: {iframe_pdf[:80]}")
            try:
                pdf_tab.goto(iframe_pdf, wait_until="commit", timeout=10_000)
            except Exception:
                pass
            wait_for_pdf(captured, timeout_s=30)
            pdf_tab.close()
            if captured:
                print("   [OA Check] ✓ Wiley epdf iframe successful!")
                return True
        else:
            print("   [OA Check] No PDF iframe in epdf reader — skipping wait")

        pdf_tab.close()
    except Exception as e:
        print(f"   [OA Check] Wiley epdf failed: {e}")
    return False


def check_open_access(page: Page, context: BrowserContext,
                      captured: list, timeout_s: int = 15) -> tuple[bool, str | None]:
    """
    Navigate to article_url (already loaded on page), look for a direct PDF link.
    If found, open it in a new tab and wait for PDF capture.
    Returns (True, pdf_url) if PDF captured, (False, pdf_url) if link found but blocked,
    (False, None) if no PDF link found.
    """
    print("\n[OA Check] Checking for open-access PDF...")

    # Try Wiley epdf pattern first
    if _try_wiley_epdf(page, context, captured, timeout_s):
        return True, None

    print("[OA Check] Scanning DOM for direct PDF link...")

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

    # Click the PDF link element on the page instead of navigating in a blank
    # new tab.  Clicking preserves Referer and sec-fetch-* headers, which
    # Cloudflare/ScienceDirect require — a blank tab gets redirected back.
    # pdf_capture's context.on("page") auto-registers hooks on any new tab.
    clicked = False
    for sel in [
        f"a[href='{pdf_href}']",
        f"a[href*='{pdf_href.split('/')[-1][:30]}']",
        "a:has-text('View PDF')",
        "a:has-text('Download PDF')",
        "a[href$='.pdf']",
        "a[href*='/pdf']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [OA Check] Clicked PDF link: {sel}")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        # Fallback: open via window.open (preserves opener/referer)
        print(f"   [OA Check] Clicking failed — using window.open")
        page.evaluate(f"window.open('{pdf_href}', '_blank')")

    if not captured:
        # Atypon CDN (Wiley/NEJM/BMJ) is consistently slower than 20s on cold
        # cache; give it more headroom before falling through to the auth flow.
        host = (page.url or "").lower()
        slow_atypon = any(h in host for h in ("wiley.com", "nejm.org", "bmj.com"))
        wait_for_pdf(captured, timeout_s=45 if slow_atypon else timeout_s)

    if captured:
        print("   [OA Check] Open access confirmed — PDF captured!")
        return True, pdf_href

    print("   [OA Check] PDF not accessible without auth.")
    return False, pdf_href
