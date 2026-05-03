# journal_club/auth_elsevier.py
import time
from urllib.parse import quote
from playwright.sync_api import Page

from journal_club.auth_oa_check import (
    detect_cloudflare_challenge, detect_elsevier_verification,
    detect_elsevier_hardblock,
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


def _click_pdf_and_wait(page: Page, captured: list, output_dir: str | None) -> bool:
    """Click the PDF button and wait for the response. That is all.

    Earlier in this debugging session we added APIRequest, urllib, in-page
    fetch, and a stealth init script. Each of those generated requests that
    the Elsevier WAF flag-counted, escalating from soft block to hard block
    over many attempts. The simple click-only flow is what worked in commit
    a988160 and earlier — and it is what works in the user is regular Chrome.
    """
    from journal_club.pdf_capture import wait_for_pdf

    # Bail if the article page itself is the hard-block (residual WAF flag
    # from earlier session). Wait for it to expire then retry.
    if detect_elsevier_hardblock(page):
        try:
            url = page.url
        except Exception:
            url = "(unknown)"
        print(f"   [Elsevier] Article page is hard-blocked — WAF flag in effect ({url[:80]})")
        print(f"   [Elsevier] Wait several hours for the rate-limit flag to expire, then retry")
        return False

    sel = _pdf_button(page)
    if not sel:
        try:
            title = page.title() or ""
        except Exception:
            title = ""
        print(f"   [Elsevier] No PDF button found (title={title[:60]!r}, url={page.url[:80]!r})")
        if title.strip() == "ScienceDirect" or detect_elsevier_hardblock(page):
            print(f"   [Elsevier] Page looks like hard-block, not real article")
        return False

    # Capture pre-click state for diagnostics
    try:
        href_before = _get_pdf_href(page, sel)
    except Exception:
        href_before = "(unreadable)"
    tabs_before = len(page.context.pages)
    url_before = page.url
    print(f"   [Elsevier] Pre-click: {tabs_before} tab(s), pdf href={href_before[:80] if href_before else None!r}")

    try:
        page.click(sel, timeout=5000)
        print(f"   [Elsevier] Clicked PDF button: {sel}")
    except Exception as e:
        print(f"   [Elsevier] PDF click failed ({sel}): {e}")
        return False

    # Diagnostics: did the click do ANYTHING?
    time.sleep(3)
    tabs_after = len(page.context.pages)
    try:
        url_after = page.url
    except Exception:
        url_after = "(unreadable)"
    print(f"   [Elsevier] Post-click +3s: {tabs_after} tab(s), main page url={'changed' if url_after != url_before else 'unchanged'} ({url_after[:80]})")

    # Wait for capture via:
    #  - direct PDF response intercepted by pdf_capture hooks (route hook on
    #    pdf.sciencedirectassets.com fires when Chrome follows the redirect), or
    #  - reader tab opened by ScienceDirect that we follow.
    _check_reader_tabs(page, captured)
    if not captured:
        wait_for_pdf(captured, timeout_s=45, output_dir=output_dir)
    if not captured:
        _check_reader_tabs(page, captured)
        wait_for_pdf(captured, timeout_s=20, output_dir=output_dir)

    if captured:
        return True

    # Last resort: if Chrome ended on a CF/Elsevier challenge page, prompt user.
    try:
        if detect_cloudflare_challenge(page) or detect_elsevier_verification(page):
            kind = "Cloudflare" if detect_cloudflare_challenge(page) else "Elsevier verification"
            print(f"   [Elsevier] {kind} page detected — prompting user")
            emit_cloudflare_alert(page)
            wait_for_pdf_or_user_action(captured, timeout_s=180)
    except Exception:
        pass

    return bool(captured)



def _check_reader_tabs(page: Page, captured: list) -> None:
    """Check any open tabs other than the article page for PDF or challenge content."""
    other_tabs = [p for p in page.context.pages if p != page]
    if not other_tabs:
        return
    print(f"   [Elsevier] {len(other_tabs)} other tab(s) open:")
    for p in other_tabs:
        try:
            t_url = p.url
        except Exception:
            t_url = "(unreadable)"
        try:
            t_title = p.title()
        except Exception:
            t_title = "(unreadable)"
        print(f"   [Elsevier]   - title={t_title[:50]!r} url={t_url[:80]!r}")

    for p in other_tabs:
        if captured:
            return
        try:
            purl = p.url
        except Exception:
            continue
        try:
            p.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass

        # CF challenge / Elsevier hardblock can land on the new tab
        try:
            if detect_cloudflare_challenge(p):
                print(f"   [Elsevier] Cloudflare challenge on tab {purl[:60]!r} — alerting user")
                emit_cloudflare_alert(p)
                wait_for_cf_clear(p)
                if captured:
                    return
        except Exception:
            pass
        try:
            if detect_elsevier_hardblock(p):
                print(f"   [Elsevier] Hardblock on tab {purl[:60]!r}")
                continue
        except Exception:
            pass

        # If the tab is on a Reader / PDF URL, try clicking the embedded
        # download button (in case Chrome's PDF viewer is showing it inline).
        if any(x in purl for x in ('reader.elsevier.com', 'sciencedirectassets',
                                    'showpdf', 'pdfft', '/pdf/')):
            for dl_sel in [
                "a[href*='pdfft']", "a[href*='showPdf']",
                "button[aria-label='Download PDF']", "button[title='Download']",
                "button:has-text('Download')", "a:has-text('Download')", "#download-btn",
            ]:
                try:
                    p.click(dl_sel, timeout=3000)
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
        print(f"   [Elsevier] No PDF captured — final URL: {page.url[:80]}")
