# journal_club/auth_openathens.py
import re
import time
from urllib.parse import urlparse, quote
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies
from journal_club.pdf_capture import wait_for_pdf


# ── Institution login button selectors (generic fallback flow) ────────────────

_INSTITUTION_BTN_SELS = [
    "a:has-text('Access through your institution')",
    "button:has-text('Access through your institution')",
    "a:has-text('Log in via your institution')",
    "button:has-text('Log in via your institution')",
    "a:has-text('Institutional access')",
    "a:has-text('Institutional login')",
    "button:has-text('Institutional login')",
    "a:has-text('Log in via OpenAthens')",
    "button:has-text('Log in via OpenAthens')",
    "a:has-text('Sign in via your institution')",
    "[data-test='institution-login']",
    "[data-id='log-in-through-your-institution']",
    "a[href*='openathens']",
    "a[href*='shibboleth']",
    "a[href*='wayf']",
    "a:has-text('Log in')",
    "button:has-text('Log in')",
]

# Institution search input selectors — Atypon-specific first, then generic
_INSTITUTION_INPUT_SELS = [
    "input.ms-inv",                   # Atypon platform (NEJM, Wiley, BMJ, OUP ssostart)
    'input[placeholder*="nstitut"]',
    'input[placeholder*="niversit"]',
    'input[placeholder*="rganiz"]',
    'input[name="org"]',
    'input[type="search"]',
    'input[type="text"]',
]

# Institution result selectors — ordered by specificity
_INSTITUTION_RESULT_SELS = [
    "a.sso-institution",                              # Atypon platform (NEJM, Wiley, BMJ, OUP)
    "div.ms-res-item a",                              # Atypon dropdown link inside item
    "div.ms-res-item",                                # Atypon dropdown item itself
    "a:has-text('Hebrew University of Jerusalem')",
    "a:has-text('Hebrew University')",
    "li:has-text('Hebrew University')",
    "[role='option']:has-text('Hebrew')",
    "button:has-text('Hebrew University')",
    ".result:has-text('Hebrew')",
]


# ── Private helpers ───────────────────────────────────────────────────────────

def _click_access_through_institution(page: Page) -> None:
    for sel in _INSTITUTION_BTN_SELS:
        try:
            page.click(sel, timeout=5000)
            print(f"   [OA] Clicked institution button: {sel}")
            time.sleep(3)
            return
        except Exception:
            continue
    print("   [OA] No institution login button found")


def _select_huji_on_wayfinder(page: Page) -> None:
    """Type HUJI into the institution search box and click the result."""
    dismiss_cookies(page)
    time.sleep(1)

    # Type into the institution search field
    for sel in _INSTITUTION_INPUT_SELS:
        try:
            page.click(sel, timeout=3000)
            page.fill(sel, "")
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [OA] Typed institution into: {sel}")
            # Wait for dropdown to populate
            try:
                page.wait_for_selector("a.sso-institution, div.ms-res-item", timeout=5000)
                print("   [OA] Dropdown appeared")
            except Exception:
                time.sleep(2)
            break
        except Exception:
            continue

    # Click the HUJI result
    for sel in _INSTITUTION_RESULT_SELS:
        try:
            page.click(sel, timeout=5000)
            print(f"   [OA] Selected institution: {sel}")
            time.sleep(2)
            return
        except Exception:
            continue
    print("   [OA] Could not find HUJI in results — may need manual selection")


def _build_sso_url(article_url: str) -> str | None:
    """Build a direct ssostart URL for known Atypon-platform publishers."""
    parsed = urlparse(article_url)
    host = parsed.hostname or ""
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query
    # Encode as a URI component: / is safe, but ? = & must be percent-encoded
    # so they don't become additional query params on the ssostart URL itself.
    encoded = quote(path, safe="/")
    if "onlinelibrary.wiley.com" in host:
        return f"https://{host}/action/ssostart?redirectUri={encoded}"
    if "nejm.org" in host:
        return f"https://www.nejm.org/action/ssostart?redirectUri={encoded}"
    if "bmj.com" in host:
        return f"https://www.bmj.com/action/ssostart?redirectUri={encoded}"
    if "academic.oup.com" in host:
        return f"https://academic.oup.com/action/ssostart?redirectUri={encoded}"
    return None


def _find_pdf_url(page: Page, article_url: str) -> str | None:
    """
    Extract the best PDF download URL from the authenticated article page.

    Priority:
      1. DOM link with ``?download=true``     — NEJM  (/doi/pdf/DOI?download=true)
      2. DOM ``/pdfdirect/`` link             — Wiley / BMJ / OUP
      3. Constructed ``/doi/pdfdirect/DOI``   — Atypon fallback
      4. Any DOM link whose text mentions PDF
    """
    # Steps 1 & 2: DOM check
    try:
        dom_pdf = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const dl = links.find(a =>
                a.href.includes('/doi/pdf') && a.href.includes('download=true'));
            if (dl) return {url: dl.href, how: 'dom:download=true'};
            const direct = links.find(a => a.href.includes('/pdfdirect/'));
            if (direct) return {url: direct.href, how: 'dom:pdfdirect'};
            return null;
        }""")
        if dom_pdf:
            print(f"   [OA] PDF link ({dom_pdf['how']}): {dom_pdf['url'][:80]}")
            return dom_pdf['url']
    except Exception as e:
        print(f"   [OA] DOM pdf-link eval error: {e}")

    # Step 3: construct from DOI
    parsed = urlparse(article_url)
    doi_match = re.search(r'/doi/(?:full|abs|pdf(?:direct)?)?/?(.+?)(?:\?|$)', parsed.path)
    if doi_match:
        doi = doi_match.group(1).strip('/')
        pdf_url = f"{parsed.scheme}://{parsed.hostname}/doi/pdfdirect/{doi}"
        print(f"   [OA] Constructed pdfdirect: {pdf_url[:80]}")
        return pdf_url

    # Step 4: any DOM link whose text says "pdf"
    try:
        fallback = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const a = links.find(l =>
                l.href.includes('pdf') &&
                (l.innerText || l.textContent || '').toLowerCase().includes('pdf'));
            return a ? a.href : null;
        }""")
        if fallback:
            print(f"   [OA] DOM fallback PDF link: {fallback[:80]}")
        return fallback
    except Exception:
        return None


def _fetch_pdf_in_tab(page: Page, pdf_url: str, captured: list) -> None:
    """Open pdf_url in a new tab and wait for the Chrome extension to deliver bytes."""
    pdf_tab = page.context.new_page()

    def _log_response(resp):
        ct = resp.headers.get("content-type", "")
        # Only log PDF / extension responses — skip CSS / JS / images
        if "pdf" in ct or "octet-stream" in ct or "chrome-extension" in resp.url:
            print(f"   [pdftab] {resp.status} {ct[:40]} <- {resp.url[:70]}")

    pdf_tab.on("response", _log_response)

    for attempt in (1, 2):
        try:
            pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
        except Exception as e:
            # Navigation raises when the response is a file download — that's OK
            print(f"   [pdftab] goto raised (attempt {attempt}, may be download): {e}")
        time.sleep(3)
        if wait_for_pdf(captured, timeout_s=30 if attempt == 1 else 20):
            return
        if attempt == 1:
            print("   [OA] Retrying PDF navigation...")


# ── Public entry point ────────────────────────────────────────────────────────

def authenticate_openathens(page: Page, article_url: str, email: str, password: str,
                             captured: list) -> str | None:
    """
    Generic OpenAthens / Atypon SSO auth flow for NEJM, BMJ, OUP, Wiley, etc.

    Returns the PDF URL that was navigated to (or None), so download.py can use
    it as a fallback if the captured list is still empty after the browser closes.
    """
    print(f"\n[OA Generic Auth] Article: {article_url[:60]}")

    sso_url = _build_sso_url(article_url)
    if sso_url:
        # Navigate directly to the publisher's ssostart page
        print(f"   [OA] SSO URL: {sso_url[:100]}")
        page.goto(sso_url, wait_until="domcontentloaded")
        time.sleep(3)
        dismiss_cookies(page)

        # Switch to Institutional tab if the page shows Individual by default
        for sel in ["a:has-text('Institutional')", "button:has-text('Institutional')",
                    "[role='tab']:has-text('Institutional')"]:
            try:
                page.click(sel, timeout=3000)
                print(f"   [OA] Clicked institutional tab: {sel}")
                time.sleep(2)
                break
            except Exception:
                continue

        # Uncheck SeamlessAccess to force a fresh SAML exchange instead of a
        # silently cached session that may be expired or unprivileged.
        try:
            page.uncheck("input.institution-preference-userconsent-checkbox", timeout=3000)
            print("   [OA] Unchecked SeamlessAccess (force fresh SAML)")
        except Exception:
            try:
                page.evaluate("""() => {
                    const cb = document.querySelector(
                        '.institution-preference-userconsent-checkbox');
                    if (cb && cb.checked) cb.click();
                }""")
            except Exception:
                pass
        time.sleep(1)

        # Institution search is on the ssostart page itself for Atypon
        _select_huji_on_wayfinder(page)
        time.sleep(3)
    else:
        # Generic: navigate to article and click through to institution login
        page.goto(article_url, wait_until="domcontentloaded")
        time.sleep(2)
        dismiss_cookies(page)
        _click_access_through_institution(page)

    print(f"   [OA] After selection: {page.url[:80]}")

    # Wait for an auth redirect: huji.ac.il (HUJI IdP), openathens/wayfinder (IdP chooser).
    # For Atypon SAML, the exchange goes through iam.atypon.com automatically — the page
    # may already be past it when we start polling, which is fine (timeout is harmless).
    try:
        page.wait_for_function(
            """() => {
                const u = window.location.href;
                return u.includes('wayfinder') ||
                       u.includes('openathens') ||
                       u.includes('huji.ac.il');
            }""",
            timeout=30_000,
        )
        current = page.url
        print(f"   [OA] Auth redirect: {current[:80]}")
        if "wayfinder" in current or "openathens" in current:
            _select_huji_on_wayfinder(page)
    except Exception:
        pass  # Atypon SAML completes silently — timeout here is expected

    wait_for_huji_and_login(page, email, password)

    # Wait for the browser to land back on the journal site
    print("\n[OA Generic] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => {
                const u = window.location.href;
                return !u.includes('huji.ac.il') &&
                       !u.includes('openathens') &&
                       !u.includes('wayfinder') &&
                       !u.includes('login') &&
                       !u.includes('ssostart');
            }""",
            timeout=90_000,
        )
        print(f"   Back on journal: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    print(f"   Authenticated page: {page.title()[:80]}")

    # Extract and fetch PDF
    print("\n[OA Generic] Extracting PDF URL from authenticated page...")
    pdf_url = _find_pdf_url(page, article_url)

    if pdf_url:
        print(f"   PDF URL: {pdf_url[:80]}")
        _fetch_pdf_in_tab(page, pdf_url, captured)
    else:
        # Last resort: click a Download PDF button in the article DOM
        print("   No PDF URL found — trying Download PDF click...")
        for sel in ["a:has-text('Download PDF')", "button:has-text('Download PDF')",
                    "a:has-text('PDF')", "[aria-label*='PDF']", "a[href$='.pdf']"]:
            try:
                page.click(sel, timeout=5000)
                print(f"   Clicked: {sel}")
                break
            except Exception:
                continue

    return pdf_url
