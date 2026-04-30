# journal_club/auth_elsevier.py
import time
from urllib.parse import quote
from playwright.sync_api import Page

from journal_club.auth_oa_check import detect_cloudflare_challenge, emit_cloudflare_alert, wait_for_cf_clear
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


def _click_pdf_and_wait(page: Page, captured: list, output_dir: str | None) -> bool:
    """Navigate the main page to the PDF URL (avoids CF blocking new tabs)."""
    from journal_club.pdf_capture import wait_for_pdf

    sel = _pdf_button(page)
    if not sel:
        print("   [Elsevier] No PDF button found on page")
        return False

    # Extract the PDF URL first so we can navigate the main page to it directly.
    # Opening pdfft URLs in a new tab gets hard-blocked by Cloudflare because the
    # new tab has no warm session. The main page already has auth cookies + CF standing.
    pdf_href = _get_pdf_href(page, sel)
    if pdf_href and any(x in pdf_href for x in ('pdfft', 'showPdf', '/doi/pdf')):
        print(f"   [Elsevier] Navigating main page to PDF URL: {pdf_href[:80]}")
        try:
            page.goto(pdf_href, wait_until="commit", timeout=30_000)
        except Exception as e:
            # Download-triggered navigations raise — pdf_capture hooks still fire.
            print(f"   [Elsevier] PDF nav raised (expected for download): {e}")

        # Check for a visible CF challenge first
        if detect_cloudflare_challenge(page):
            print("   [Elsevier] CF challenge on PDF page — alerting user")
            emit_cloudflare_alert(page)
            wait_for_cf_clear(page)
            wait_for_pdf(captured, timeout_s=30, output_dir=output_dir)
            return bool(captured)

        # Short wait — if it's a clean PDF response, capture fires almost immediately
        wait_for_pdf(captured, timeout_s=15, output_dir=output_dir)

        if not captured:
            # CF sometimes hard-blocks without a visible challenge (no "Just a Moment"
            # page, no iframe) — just a silent redirect. Bring Chrome to front so the
            # user can complete any invisible verification or click through manually.
            print("   [Elsevier] PDF not captured after 15s — prompting user to check Chrome")
            emit_cloudflare_alert(page)
            wait_for_cf_clear(page, timeout_ms=120_000)
            wait_for_pdf(captured, timeout_s=30, output_dir=output_dir)

        return bool(captured)

    # Fallback: click the button (may open new tab or trigger download directly)
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
