# journal_club/auth_oa_check.py
"""
Open-access check: try to find + fetch a PDF link directly in the DOM.
Must be called BEFORE any auth flow.
Returns True if PDF was captured, False otherwise.
"""
import json
import re
import sys
import threading
import time
from playwright.sync_api import Page, BrowserContext

from journal_club.pdf_capture import wait_for_pdf

# Module-level state for the stdin command listener (one per sidecar process)
_cf_page_ref: list = [None]
_stdin_listener_started = False


def emit_cloudflare_alert(page: Page) -> None:
    """Emit structured event so the desktop UI can prompt the user to solve CF.

    Also brings the Chrome tab to the foreground and starts a background thread
    that listens for bring_to_front commands written to stdin by Tauri.
    """
    global _stdin_listener_started
    _cf_page_ref[0] = page

    payload = {
        "type": "cloudflare_challenge",
        "message": "Human verification required \u2014 look at the Chrome window and complete the check, then leave it alone.",
    }
    print(json.dumps(payload), flush=True)
    sys.stdout.flush()

    try:
        page.bring_to_front()
    except Exception:
        pass

    if not _stdin_listener_started:
        _stdin_listener_started = True

        def _listen():
            while True:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    cmd = json.loads(line.strip())
                    if cmd.get("cmd") == "bring_to_front" and _cf_page_ref[0] is not None:
                        try:
                            _cf_page_ref[0].bring_to_front()
                        except Exception:
                            pass
                except Exception:
                    pass

        threading.Thread(target=_listen, daemon=True).start()


def detect_cloudflare_challenge(page: Page) -> bool:
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    if "just a moment" in title or "cloudflare" in title:
        return True
    try:
        if page.locator("input[name='cf-turnstile-response']").count() > 0:
            return True
    except Exception:
        pass
    try:
        if page.locator("iframe[src*='challenges.cloudflare.com']").count() > 0:
            return True
    except Exception:
        pass
    return False


def detect_elsevier_verification(page: Page) -> bool:
    """Detect Elsevier's 'Request Verification: In Progress' bot-block page."""
    try:
        title = (page.title() or "").lower()
        if "verification" in title or "request verification" in title:
            return True
    except Exception:
        pass
    try:
        # Look for the heading or body text that identifies the page
        if page.locator("h1:has-text('Request Verification')").count() > 0:
            return True
        if page.locator("text=Request Verification: In Progress").count() > 0:
            return True
    except Exception:
        pass
    return False


def detect_elsevier_hardblock(page: Page) -> bool:
    """Detect Elsevier's hard-block error page ('There was a problem providing
    the content you requested'). This page has NO interactive challenge — it's
    served when the WAF has flagged the session/IP. No amount of waiting or
    clicking will bypass it from the same session.
    """
    try:
        if page.locator("h1:has-text('There was a problem providing the content')").count() > 0:
            return True
        if page.locator("text=There was a problem providing the content you requested").count() > 0:
            return True
    except Exception:
        pass
    return False


def detect_elsevier_hardblock_html(html_bytes: bytes) -> bool:
    """Same as detect_elsevier_hardblock but works on raw response bytes.
    Used when we have an APIRequest response body without a live Page object."""
    try:
        text = html_bytes.decode("utf-8", errors="ignore")
        return "There was a problem providing the content you requested" in text
    except Exception:
        return False


def wait_for_cf_clear(page: Page, timeout_ms: int = 90_000) -> bool:
    try:
        page.wait_for_function(
            "() => !document.title.toLowerCase().includes('just a moment') "
            "&& !document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')",
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def wait_for_pdf_or_user_action(captured: list, timeout_s: int = 180) -> bool:
    """Poll until PDF is captured or timeout. Used when waiting for user to
    complete verification in Chrome. Keeps the browser session alive."""
    import time
    start = time.time()
    while time.time() - start < timeout_s:
        if captured:
            return True
        time.sleep(2)
    return bool(captured)


def _try_wiley_pdfdirect(page: Page, context: BrowserContext, captured: list) -> bool:
    """For Wiley OA articles, /doi/pdfdirect/{doi} streams the PDF binary
    directly without requiring institutional auth. Try this before falling
    through to HUJI Shibboleth.
    """
    url = page.url
    m = re.search(r"wiley\.com/doi/(?:abs/|full/|epdf/)?(?P<doi>10\.\d{4,9}/[^/?#]+)", url)
    if not m:
        return False
    doi = m.group("doi")
    pdfdirect = f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}"
    print(f"   [OA Check] Trying Wiley pdfdirect: {pdfdirect[:80]}")
    try:
        pdf_tab = context.new_page()
        try:
            pdf_tab.goto(pdfdirect, wait_until="commit", timeout=15_000)
        except Exception:
            # Download-triggered navigations raise — pdf_capture hooks still fire.
            pass
        if detect_cloudflare_challenge(pdf_tab):
            print("   [OA Check] Cloudflare gate on pdfdirect — alerting user")
            emit_cloudflare_alert(pdf_tab)
            wait_for_cf_clear(pdf_tab)
        # Bail early if Wiley redirected to a login/SSO page (paywalled article)
        try:
            cur = pdf_tab.url or ""
        except Exception:
            cur = ""
        if any(s in cur for s in ("/action/ssostart", "/action/showLogin", "/action/doLogin")):
            print(f"   [OA Check] pdfdirect redirected to login ({cur[:80]}) — not OA")
            try: pdf_tab.close()
            except Exception: pass
            return False
        wait_for_pdf(captured, timeout_s=20)
        try:
            pdf_tab.close()
        except Exception:
            pass
        if captured:
            print("   [OA Check] \u2713 Wiley pdfdirect successful!")
            return True
    except Exception as e:
        print(f"   [OA Check] Wiley pdfdirect failed: {e}")
    return False

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

    # Surface CF challenge on the article page itself before any attempts
    if detect_cloudflare_challenge(page):
        print("   [OA Check] Cloudflare gate on article page — alerting user")
        emit_cloudflare_alert(page)
        wait_for_cf_clear(page)

    # Wiley OA: pdfdirect streams the PDF binary, no auth needed
    if _try_wiley_pdfdirect(page, context, captured):
        return True, None

    # Fallback: Wiley epdf reader (rarely yields PDF iframe)
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
