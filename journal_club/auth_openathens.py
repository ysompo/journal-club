# journal_club/auth_openathens.py
import re
import time
from urllib.parse import urlparse, quote
from playwright.sync_api import Page

from journal_club.auth_oa_check import detect_cloudflare_challenge, emit_cloudflare_alert, wait_for_cf_clear
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


def _select_huji_on_wayfinder(page: Page, _retry: bool = False) -> None:
    """Type HUJI into the institution search box and click the result."""
    import datetime as _dt
    print(f"   [OA] _select_huji_on_wayfinder starting (URL: {page.url[:60]})")
    sys.stdout.flush()

    # Race guard: caller may have captured a wayfinder URL that has since
    # redirected to the HUJI IdP. If we're already at the HUJI login page,
    # there is no institution dropdown to interact with — bail out so the
    # credential filler (login_huji) can run instead of blocking the user.
    if "huji.ac.il" in page.url or "loginuserpass" in page.url:
        print("   [OA] Already at HUJI IdP — skipping wayfinder selection")
        return

    # Screenshot on entry so we can see what the wayfinder page looks like
    try:
        _ts = _dt.datetime.now().strftime("%H%M%S")
        page.screenshot(path=f"debug_oa_wayfinder_{_ts}.png")
        print(f"   [OA] Wayfinder screenshot: debug_oa_wayfinder_{_ts}.png")
    except Exception:
        pass

    dismiss_cookies(page)
    time.sleep(1)

    for search_term in ("Hebrew University of Jerusalem", "Hebrew University"):
        # Type into the institution search field
        for sel in _INSTITUTION_INPUT_SELS:
            try:
                page.click(sel, timeout=3000)
                page.fill(sel, "")
                page.type(sel, search_term, delay=60)
                print(f"   [OA] Typed '{search_term}' into: {sel}")
                # Wait longer — Atypon API can be slow on first load
                try:
                    page.wait_for_selector(
                        "a.sso-institution, div.ms-res-item", timeout=10_000)
                    print("   [OA] Dropdown appeared")
                except Exception:
                    time.sleep(3)
                break
            except Exception:
                continue

        # Screenshot after typing to see dropdown state
        try:
            _ts2 = _dt.datetime.now().strftime("%H%M%S")
            page.screenshot(path=f"debug_oa_dropdown_{_ts2}.png")
            print(f"   [OA] Dropdown screenshot: debug_oa_dropdown_{_ts2}.png")
        except Exception:
            pass

        # Click the HUJI result
        for sel in _INSTITUTION_RESULT_SELS:
            try:
                page.click(sel, timeout=5000)
                print(f"   [OA] Selected institution: {sel}")
                time.sleep(2)
                return  # success
            except Exception:
                continue

        # Clear the field before retrying with shorter term
        print(f"   [OA] No result for '{search_term}' — retrying...")
        for sel in _INSTITUTION_INPUT_SELS:
            try:
                page.fill(sel, "")
                break
            except Exception:
                continue
        time.sleep(1)

    # Both terms failed. Most common cause is a Cloudflare challenge throttling
    # the autocomplete API — surface that to the user instead of silently
    # giving up. _retry guards against infinite recursion if CF clears but
    # something else is still wrong.
    if not _retry and detect_cloudflare_challenge(page):
        print("   [OA] Cloudflare challenge detected on wayfinder — alerting user")
        emit_cloudflare_alert(page)
        if wait_for_cf_clear(page):
            print("   [OA] Cloudflare challenge cleared — re-entering wayfinder selection")
            return _select_huji_on_wayfinder(page, _retry=True)
        else:
            print("   [OA] Cloudflare challenge not cleared in 90s")

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


def _capture_response_body_pdf(page: Page, pdf_url: str, captured: list) -> bool:
    """Capture PDF via route interception (response body, not download). Returns True if successful."""
    pdf_tab = page.context.new_page()
    pdf_data = []

    def intercept_route(route, request):
        try:
            response = route.fetch()
            body = response.body()
            if body[:4] == b'%PDF':
                pdf_data.append(body)
                print(f"   [pdftab/route] ✓ Captured {len(body):,} bytes via route interception")
        except Exception as e:
            print(f"   [pdftab/route] Error intercepting: {e}")
        route.continue_()

    pdf_tab.route("**/*.pdf", intercept_route)
    try:
        pdf_tab.goto(pdf_url, wait_until="networkidle", timeout=20_000)
    except Exception as e:
        print(f"   [pdftab/route] Navigation error: {e}")

    if pdf_data and not captured:
        captured.append(pdf_data[0])
        print(f"   [pdftab] ✓ PDF captured via response-body interception: {len(pdf_data[0]):,} bytes")
        pdf_tab.close()
        return True

    pdf_tab.close()
    return False


def _capture_download_pdf(page: Page, pdf_url: str, captured: list, output_dir: str = None) -> bool:
    """Try to capture PDF via file download. Returns True if successful, False otherwise."""
    import os as _os
    import tempfile as _tmp
    from playwright.sync_api import TimeoutError as _PlaywrightTimeout

    pdf_tab = page.context.new_page()

    def _log_response(resp):
        ct = resp.headers.get("content-type", "")
        # Only log PDF / extension responses — skip CSS / JS / images
        if "pdf" in ct or "octet-stream" in ct or "chrome-extension" in resp.url:
            print(f"   [pdftab] {resp.status} {ct[:40]} <- {resp.url[:70]}")

    pdf_tab.on("response", _log_response)

    for attempt in (1, 2):
        try:
            with pdf_tab.expect_download(timeout=180_000) as dl_info:
                try:
                    pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
                except Exception as e:
                    # Navigation raises when the response is a file download — that's OK
                    print(f"   [pdftab] goto raised (attempt {attempt}, may be download): {e}")
            dl = dl_info.value
            tmp_path = _os.path.join(_tmp.mkdtemp(), dl.suggested_filename or "article.pdf")
            print(f"   [pdftab] Saving download: {dl.suggested_filename}")
            dl.save_as(tmp_path)  # blocks until complete; browser stays open
            with open(tmp_path, "rb") as f:
                body = f.read()
            if body[:4] == b'%PDF':
                captured.append(body)
                print(f"   [pdftab] ✓ PDF captured via file download: {len(body):,} bytes")
                pdf_tab.close()
                return True
        except _PlaywrightTimeout:
            # No file-download event — PDF may come via response hooks (navigation)
            print(f"   [pdftab] No download event (attempt {attempt}) — will try response-body fallback")
        except Exception as e:
            print(f"   [pdftab] Error (attempt {attempt}): {e}")

        if wait_for_pdf(captured, timeout_s=20, output_dir=output_dir):
            pdf_tab.close()
            return True
        if attempt == 1:
            print("   [OA] Retrying PDF navigation...")

    pdf_tab.close()
    return False


def _fetch_pdf_in_tab(page: Page, pdf_url: str, captured: list, output_dir: str = None) -> None:
    """
    Try to capture PDF via download first (works for Wiley, BMJ, OUP, etc.).
    If download fails or times out, fall back to response-body interception
    (works for NEJM, Lancet, and other publishers serving PDFs as response bodies).
    """
    print(f"   [pdftab] Attempting download-based capture...")
    if _capture_download_pdf(page, pdf_url, captured, output_dir):
        return  # Success via download

    print(f"   [pdftab] Download approach failed — attempting response-body fallback...")
    _capture_response_body_pdf(page, pdf_url, captured)


# ── Public entry point ────────────────────────────────────────────────────────

def authenticate_openathens(page: Page, article_url: str, email: str, password: str,
                             captured: list, output_dir: str = None) -> str | None:
    """
    Generic OpenAthens / Atypon SSO auth flow for NEJM, BMJ, OUP, Wiley, etc.

    Returns the PDF URL that was navigated to (or None), so download.py can use
    it as a fallback if the captured list is still empty after the browser closes.
    """
    import sys
    print(f"\n[OA Generic Auth] Article: {article_url[:60]}")
    print(f"[OA] Browser: {page.context.browser.browser_type.name}")
    sys.stdout.flush()

    # If the Chrome extension already captured the PDF (cached session), skip auth entirely
    if captured:
        print("   [OA] PDF captured during navigation — skipping auth")
        return None

    sso_url = _build_sso_url(article_url)
    if sso_url:
        # For Wiley/Atypon: warm up Cloudflare session like we do for ScienceDirect
        if "onlinelibrary.wiley.com" in sso_url:
            print("[OA Wiley] Warming up Cloudflare session via homepage...")
            try:
                page.goto("https://www.onlinelibrary.wiley.com",
                          wait_until="domcontentloaded", timeout=20_000)
                time.sleep(3)
                print(f"   Homepage loaded: {page.title()[:60]}")
            except Exception as _e:
                print(f"   Homepage warm-up error (continuing): {_e}")

        # Navigate directly to the publisher's ssostart page
        # Try "commit" first (page started responding), then fallback to "domcontentloaded"
        print(f"   [OA] SSO URL: {sso_url[:100]}")
        try:
            page.goto(sso_url, wait_until="commit", timeout=20_000)
            print("   [OA] Page committed (response started)")
        except Exception as e:
            print(f"   [OA] SSO commit error: {e} — trying domcontentloaded...")
            try:
                page.goto(sso_url, wait_until="domcontentloaded", timeout=30_000)
                print("   [OA] Page domcontentloaded")
            except Exception as e2:
                print(f"   [OA] SSO navigation error (continuing): {e2}")
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
        print("   [OA] Selecting HUJI on ssostart page...")
        _select_huji_on_wayfinder(page)
        print(f"   [OA] After HUJI selection: {page.url[:80]}")
        time.sleep(3)
    else:
        # Generic: navigate to article and click through to institution login
        try:
            print("   [OA] Navigating to article...")
            page.goto(article_url, wait_until="domcontentloaded", timeout=30_000)
            print(f"   [OA] Article loaded: {page.url[:80]}")
        except Exception as e:
            print(f"   [OA] Article navigation error (continuing): {e}")
        time.sleep(2)
        dismiss_cookies(page)
        print("   [OA] Clicking institution login button...")
        _click_access_through_institution(page)
        print(f"   [OA] After institution click: {page.url[:80]}")

    import sys
    sys.stdout.flush()
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
    page.goto(article_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    print(f"   Authenticated page: {page.title()[:80]}")

    # Extract and fetch PDF
    print("\n[OA Generic] Extracting PDF URL from authenticated page...")
    pdf_url = _find_pdf_url(page, article_url)

    if pdf_url:
        print(f"   PDF URL: {pdf_url[:80]}")
        _fetch_pdf_in_tab(page, pdf_url, captured, output_dir)
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
