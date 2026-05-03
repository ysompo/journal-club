# journal_club/auth_elsevier.py
import time
from urllib.parse import quote
from playwright.sync_api import Page

from journal_club.auth_oa_check import (
    detect_cloudflare_challenge, detect_elsevier_verification,
    emit_cloudflare_alert, wait_for_cf_clear, wait_for_pdf_or_user_action,
)
from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

_HUJI_ENTITY_ID = "https://idp.huji.ac.il/idp/shibboleth"

_PDF_SELS = [
    "a[href*='showPdf']",
    "a[href*='pdfft']",
    "a[href*='/doi/pdf']",
    "a:has-text('View PDF')",
    "button:has-text('View PDF')",
    "a:has-text('Download PDF')",
    "button:has-text('Download PDF')",
]

_HUJI_RESULT_SELS = [
    "[role='option']:has-text('Hebrew')",
    "li:has-text('Hebrew University')",
    "span:has-text('Hebrew University of Jerusalem')",
    "a:has-text('Hebrew University')",
    "button:has-text('Hebrew University')",
]


def _build_sd_institution_login(article_url: str) -> str:
    """Build ScienceDirect institutional-login URL.
    Reliably redirects to id.elsevier.com/as/authorization.oauth2."""
    return (
        "https://www.sciencedirect.com/user/institution/login"
        f"?entityID={quote(_HUJI_ENTITY_ID, safe='')}"
        f"&returnURL={quote(article_url, safe='')}"
    )


def _pdf_button(page: Page) -> str | None:
    """Return the first visible PDF selector found on the page, or None."""
    for sel in _PDF_SELS:
        try:
            if page.locator(sel).count() > 0:
                return sel
        except Exception:
            pass
    return None


def _get_pdf_href(page: Page, sel: str) -> str | None:
    """Extract the href from a PDF link element without clicking it."""
    try:
        loc = page.locator(sel).first
        href = loc.get_attribute("href")
        if href:
            # Make absolute if relative
            if href.startswith("/"):
                from urllib.parse import urlparse
                u = urlparse(page.url)
                href = f"{u.scheme}://{u.netloc}{href}"
            return href
    except Exception:
        pass
    return None


def _fetch_pdf_via_urllib(page: Page, pdf_href: str, captured: list) -> bool:
    """Download the PDF via urllib using cookies extracted from the browser.

    Elsevier's pdfft endpoint hard-blocks any client coming from the SAML/OAuth
    session inside the browser (HTML returned even for fetch()). urllib has no
    automation fingerprint, no SAML session signature — just an authenticated
    HTTP request with cookies copied from the browser context.
    """
    import urllib.request
    import urllib.error
    import http.cookiejar

    print(f"   [Elsevier] Trying urllib download with browser cookies...")
    try:
        # Pull all cookies for sciencedirect.com / elsevier.com from the context
        jar = http.cookiejar.CookieJar()
        for c in page.context.cookies():
            domain = c.get("domain", "")
            if not any(d in domain for d in ("sciencedirect.com", "elsevier.com")):
                continue
            ck = http.cookiejar.Cookie(
                version=0,
                name=c["name"],
                value=c["value"],
                port=None, port_specified=False,
                domain=domain, domain_specified=bool(domain),
                domain_initial_dot=domain.startswith("."),
                path=c.get("path", "/"), path_specified=True,
                secure=c.get("secure", False),
                expires=int(c["expires"]) if c.get("expires", -1) > 0 else None,
                discard=False, comment=None, comment_url=None, rest={},
            )
            jar.set_cookie(ck)

        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        # Mimic a normal browser request originating from the article page
        article_url = page.url
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
        headers = {
            "User-Agent": ua,
            "Accept": "application/pdf,application/x-pdf,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": article_url,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        req = urllib.request.Request(pdf_href, headers=headers)
        with opener.open(req, timeout=60) as resp:
            ct = resp.headers.get("Content-Type", "").lower()
            data = resp.read()
            print(f"   [Elsevier] urllib response: {resp.status} {ct[:40]} ({len(data):,} bytes)")
            if data[:4] == b"%PDF" or "pdf" in ct:
                if data[:4] == b"%PDF" and len(data) > 10_000:
                    print(f"   [Elsevier] ✓ urllib PDF: {len(data):,} bytes")
                    captured.append(data)
                    return True
                print(f"   [Elsevier] urllib response not a valid PDF (header: {data[:8]!r})")
            else:
                print(f"   [Elsevier] urllib returned non-PDF (likely verification HTML)")
    except urllib.error.HTTPError as e:
        print(f"   [Elsevier] urllib HTTP error: {e.code} {e.reason}")
    except Exception as e:
        print(f"   [Elsevier] urllib error: {type(e).__name__}: {e}")
    return False


def _fetch_pdf_via_js(page: Page, pdf_href: str, captured: list) -> bool:
    """Download PDF via in-page fetch() — bypasses Elsevier bot detection.

    Running fetch() from within the page's JS context means the server sees a
    normal same-origin XHR with all existing session cookies and the article
    page as Referer. No CDP navigation fingerprint, no automation signals.
    """
    import base64
    print(f"   [Elsevier] Trying in-page fetch() for PDF...")
    # Bump default timeout for this single long-running evaluate (PDF can be MB)
    prev_timeout = None
    try:
        prev_timeout = 30_000
        page.set_default_timeout(120_000)
    except Exception:
        pass
    try:
        result = page.evaluate(
            """
            async (url) => {
                try {
                    const r = await fetch(url, { credentials: 'include' });
                    const ct = r.headers.get('content-type') || '';
                    if (!r.ok || !ct.toLowerCase().includes('pdf')) {
                        return { ok: false, status: r.status, ct: ct };
                    }
                    const blob = await r.blob();
                    return await new Promise(resolve => {
                        const fr = new FileReader();
                        fr.onloadend = () => resolve({
                            ok: true,
                            data: fr.result.split(',')[1]
                        });
                        fr.onerror = () => resolve({ ok: false, error: 'FileReader error' });
                        fr.readAsDataURL(blob);
                    });
                } catch(e) {
                    return { ok: false, error: e.message };
                }
            }
            """,
            pdf_href,
        )
        if result and result.get("ok") and result.get("data"):
            pdf_bytes = base64.b64decode(result["data"])
            if len(pdf_bytes) > 10_000:
                print(f"   [Elsevier] ✓ fetch() PDF: {len(pdf_bytes):,} bytes")
                captured.append(pdf_bytes)
                return True
            print(f"   [Elsevier] fetch() response too small ({len(pdf_bytes)} bytes) — not PDF")
        else:
            print(f"   [Elsevier] fetch() not PDF: {result}")
    except Exception as e:
        print(f"   [Elsevier] fetch() error: {e}")
    finally:
        if prev_timeout is not None:
            try:
                page.set_default_timeout(prev_timeout)
            except Exception:
                pass
    return False


def _click_pdf_and_wait(page: Page, captured: list, output_dir: str | None) -> bool:
    """Download the PDF: try in-page fetch() first, fall back to click."""
    from journal_club.pdf_capture import wait_for_pdf

    sel = _pdf_button(page)
    if not sel:
        print("   [Elsevier] No PDF button found on page")
        return False

    pdf_href = _get_pdf_href(page, sel)
    if pdf_href and any(x in pdf_href for x in ('pdfft', 'showPdf', '/doi/pdf')):
        # Click the PDF link with a real user gesture — no JS overrides, no
        # window.open intercept, no urllib. Chrome handles the pdfft handshake
        # natively (correct TLS fingerprint, JS-issued crasolve token), then
        # follows the redirect to pdf.sciencedirectassets.com (the S3 CDN).
        # pdf_capture.py's route interceptor catches the S3 response and grabs
        # the real PDF bytes before any client code (or extension) touches them.
        print(f"   [Elsevier] Clicking PDF link with user gesture: {pdf_href[:80]}")
        try:
            # dispatchEvent('click', {bubbles:true}) most closely mimics a
            # human click — ScienceDirect's own JS runs and constructs a
            # legitimate request with their token.
            page.locator(sel).first.click(timeout=5000)
        except Exception as e:
            print(f"   [Elsevier] Click raised (may be download): {e}")

        # Watch for either:
        #  - PDF captured via the S3 CDN route hook in pdf_capture.py
        #  - A new tab opened by ScienceDirect that we should follow
        time.sleep(3)
        _check_reader_tabs(page, captured)

        wait_for_pdf(captured, timeout_s=30, output_dir=output_dir)
        if captured:
            return True
        _check_reader_tabs(page, captured)
        if captured:
            return True

        # Still nothing — check if we landed on a verification page on any tab
        all_pages = list(page.context.pages)
        for p in all_pages:
            try:
                if detect_cloudflare_challenge(p) or detect_elsevier_verification(p):
                    kind = "Cloudflare" if detect_cloudflare_challenge(p) else "Elsevier verification"
                    print(f"   [Elsevier] {kind} page on tab {p.url[:60]} — prompting user")
                    emit_cloudflare_alert(p)
                    wait_for_pdf_or_user_action(captured, timeout_s=180)
                    return bool(captured)
            except Exception:
                pass

        # No verification page detected but no PDF either — prompt user anyway
        print("   [Elsevier] PDF not captured after 30s — prompting user to check Chrome")
        emit_cloudflare_alert(page)
        wait_for_pdf_or_user_action(captured, timeout_s=180)
        return bool(captured)

    # No pdfft href found — click and let Chrome handle it
    try:
        page.click(sel, timeout=5000)
        print(f"   [Elsevier] Clicked PDF button: {sel}")
    except Exception as e:
        print(f"   [Elsevier] PDF click failed ({sel}): {e}")
        return False

    time.sleep(5)
    _check_reader_tabs(page, captured)
    if not captured:
        wait_for_pdf(captured, timeout_s=60, output_dir=output_dir)
    if not captured:
        _check_reader_tabs(page, captured)
        wait_for_pdf(captured, timeout_s=30, output_dir=output_dir)
    return bool(captured)


def _check_reader_tabs(page: Page, captured: list) -> None:
    """Check any open Elsevier Reader / PDF tabs and click their Download button."""
    for p in page.context.pages:
        if p == page or captured:
            continue
        purl = p.url
        if any(x in purl for x in ('reader.elsevier.com', 'sciencedirectassets',
                                    'showpdf', 'pdfft', '/pdf/')):
            print(f"   [Elsevier] Reader/PDF tab: {purl[:80]}")
            try:
                p.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            # CF challenge can appear on the PDF/reader tab itself
            if detect_cloudflare_challenge(p):
                print("   [Elsevier] Cloudflare challenge on PDF tab — alerting user")
                emit_cloudflare_alert(p)
                wait_for_cf_clear(p)
            if captured:
                return
            for dl_sel in [
                "a[href*='pdfft']", "a[href*='showPdf']",
                "button[aria-label='Download PDF']", "button[title='Download']",
                "button:has-text('Download')", "a:has-text('Download')", "#download-btn",
            ]:
                try:
                    p.click(dl_sel, timeout=5000)
                    print(f"   [Elsevier] Clicked reader download: {dl_sel}")
                    break
                except Exception:
                    continue


def _handle_elsevier_idp(page: Page) -> bool:
    """Handle id.elsevier.com auth page.

    State A: HUJI already pre-selected — click "Access through your organization".
    State B: "Find your organization" form — type Hebrew University, select result.

    Returns True if we successfully triggered a redirect toward HUJI.
    """
    time.sleep(2)
    dismiss_cookies(page)
    print(f"   [Elsevier] IdP page: {page.url[:80]}")
    print(f"   [Elsevier] IdP title: {page.title()[:60]}")

    # State A: HUJI already pre-selected — just click the button.
    # Try get_by_role first (catches <button>, <a>, and <div role="button/link">).
    for phrase in ["Access through your organization", "Access through your institution"]:
        for role in ["button", "link"]:
            try:
                loc = page.get_by_role(role, name=phrase, exact=False)
                if loc.count() > 0:
                    loc.first.click(timeout=5000)
                    print(f"   [Elsevier] State A: clicked {role!r} '{phrase}'")
                    return True
            except Exception as e:
                print(f"   [Elsevier] State A get_by_role({role!r}, {phrase!r}) failed: {e}")

    # CSS-selector fallback (handles non-semantic elements)
    for sel in [
        "button:has-text('Access through your organization')",
        "a:has-text('Access through your organization')",
        "[role='button']:has-text('Access through your organization')",
        "[role='link']:has-text('Access through your organization')",
        "button:has-text('Access through your institution')",
        "a:has-text('Access through your institution')",
    ]:
        try:
            if page.locator(sel).count() > 0:
                page.click(sel, timeout=5000)
                print(f"   [Elsevier] State A (CSS): clicked {sel!r}")
                return True
        except Exception as e:
            print(f"   [Elsevier] State A CSS click failed ({sel}): {e}")

    # State B: "Find your organization" search form
    print("   [Elsevier] State A button not found — trying State B (org search form)")
    try:
        page.wait_for_selector('input[type="text"]', state="visible", timeout=8000)
    except Exception:
        print("   [Elsevier] No text input appeared — State B unavailable")
        return False

    try:
        inp = page.locator('input[type="text"]').first
        if not inp.is_visible():
            print("   [Elsevier] input[type=text] not visible")
            return False
        inp.click(timeout=3000)
        inp.fill("")
        inp.type("Hebrew University", delay=40)
        print("   [Elsevier] State B: typed 'Hebrew University'")
    except Exception as e:
        print(f"   [Elsevier] State B typing failed: {e}")
        return False

    # Wait for autocomplete dropdown
    try:
        page.wait_for_selector(", ".join(_HUJI_RESULT_SELS), timeout=6000)
    except Exception:
        time.sleep(2)

    for sel in _HUJI_RESULT_SELS:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(timeout=3000)
                print(f"   [Elsevier] State B: selected HUJI via {sel!r}")
                return True
        except Exception:
            continue

    print("   [Elsevier] State B: HUJI not found in autocomplete results")
    return False


def authenticate_elsevier(page: Page, article_url: str, email: str, password: str,
                           captured: list, output_dir: str | None = None) -> None:
    """Clean Elsevier/ScienceDirect auth flow.

    Flow:
      1. Fast-path: PDF button already visible (cached session) → click it
      2. Navigate to institution login URL → id.elsevier.com
      3. Handle IdP page (State A: pre-selected HUJI button, State B: search form)
      4. HUJI login (Keycloak or CC IdP)
      5. Return to article → click PDF button
    """
    print(f"\n[Elsevier] Auth: {article_url[:80]}")

    if captured:
        print("   [Elsevier] PDF already captured — skipping auth")
        return

    # ── 1. Ensure we're on an Elsevier page ─────────────────────────────────
    # download.py already navigated to article_url. If that redirected to
    # id.elsevier.com, page.url contains "elsevier.com" — skip re-navigation.
    if "elsevier.com" not in page.url and "sciencedirect.com" not in page.url:
        print(f"   [Elsevier] Not on Elsevier — navigating to article...")
        try:
            page.goto(article_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"   [Elsevier] Nav error: {e}")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    time.sleep(2)
    if detect_cloudflare_challenge(page):
        emit_cloudflare_alert(page)
        wait_for_cf_clear(page)
    if captured:
        return
    dismiss_cookies(page)
    print(f"   [Elsevier] Landed: {page.url[:80]}")

    # ── 2. Fast-path: PDF already accessible (valid session cookies) ─────────
    sel = _pdf_button(page)
    if sel:
        print(f"   [Elsevier] PDF button visible ({sel}) — clicking directly")
        _click_pdf_and_wait(page, captured, output_dir)
        return

    # ── 3. Navigate to institution login URL → lands on id.elsevier.com ──────
    shib_url = _build_sd_institution_login(article_url)
    print(f"   [Elsevier] No PDF button — navigating to institution login...")
    print(f"   [Elsevier] URL: {shib_url[:120]}")
    try:
        page.goto(shib_url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        print(f"   [Elsevier] Institution login nav error: {e}")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    time.sleep(2)
    if detect_cloudflare_challenge(page):
        emit_cloudflare_alert(page)
        wait_for_cf_clear(page)
    if captured:
        return
    dismiss_cookies(page)

    # ── 4. Handle id.elsevier.com IdP page ──────────────────────────────────
    idp_ok = _handle_elsevier_idp(page)
    if not idp_ok:
        # Neither button nor form found — log diagnostic and continue anyway
        print(f"   [Elsevier] IdP handling failed — URL: {page.url[:80]}")
        try:
            page.screenshot(path="debug_elsevier_idp_fail.png")
            print("   [Elsevier] Screenshot: debug_elsevier_idp_fail.png")
        except Exception:
            pass

    # ── 5. HUJI login ────────────────────────────────────────────────────────
    # wait_for_huji_and_login waits up to 60s for huji.ac.il to appear,
    # then fills email+password and submits. Handles both CC IdP and Keycloak.
    wait_for_huji_and_login(page, email, password)

    # ── 6. Wait for return from HUJI / OAuth callback ────────────────────────
    print("   [Elsevier] Waiting to return from HUJI...")
    try:
        page.wait_for_function(
            """() => {
                const u = window.location.href;
                return !u.includes('huji.ac.il') &&
                       !u.includes('id.elsevier.com') &&
                       !u.includes('openathens') &&
                       !u.includes('login');
            }""",
            timeout=90_000,
        )
        print(f"   [Elsevier] Returned: {page.url[:80]}")
    except Exception:
        print(f"   [Elsevier] Return wait timed out. URL: {page.url[:80]}")

    # Let any OAuth round-trip through id.elsevier.com finish
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:
        pass
    time.sleep(2)
    if detect_cloudflare_challenge(page):
        emit_cloudflare_alert(page)
        wait_for_cf_clear(page)

    # ── 7. Navigate to article and click PDF ─────────────────────────────────
    try:
        page.goto(article_url, wait_until="domcontentloaded", timeout=30_000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
    except Exception as e:
        print(f"   [Elsevier] Post-auth article nav: {e}")
        try:
            page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
    time.sleep(2)

    # Reload so the authenticated session's pdfft token is freshly issued
    try:
        page.reload(wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        time.sleep(2)
    except Exception as e:
        print(f"   [Elsevier] Reload error: {e}")

    print(f"   [Elsevier] Post-auth page: {page.title()[:60]}")
    if not _click_pdf_and_wait(page, captured, output_dir):
        print(f"   [Elsevier] No PDF captured — URL: {page.url[:80]}")
        print("   [Elsevier] download.py retry loop will attempt again if needed")
