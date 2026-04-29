# journal_club/auth_elsevier.py
import time
from playwright.sync_api import Page

from journal_club.auth_oa_check import detect_cloudflare_challenge, emit_cloudflare_alert, wait_for_cf_clear
from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

# Domains that indicate we've reached an auth/IdP page
_AUTH_DOMAINS = (
    'id.elsevier.com',
    'sciencedirect.com/user/ropc',
    'openathens',
    'wayfinder',
    'huji.ac.il',
)

_INSTITUTION_INPUT_SELS = [
    'input[placeholder*="nstitut"]',
    'input[placeholder*="niversit"]',
    'input[placeholder*="rganiz"]',
    'input[name="org"]',
    'input[type="search"]',
    'input[type="text"]',
]

_INSTITUTION_RESULT_SELS = [
    "span:has-text('Hebrew University of Jerusalem')",
    "a:has-text('Hebrew University of Jerusalem')",
    "a:has-text('Hebrew University')",
    "li:has-text('Hebrew University')",
    "[role='option']:has-text('Hebrew')",
    "button:has-text('Hebrew University')",
    ".result:has-text('Hebrew')",
]


def _check_reader_tabs(page, captured: list) -> None:
    """Look for any open Elsevier Reader / PDF tabs and click their Download button."""
    for p in page.context.pages:
        if p == page:
            continue          # skip the article page itself, keep scanning other tabs
        if captured:
            return
        purl = p.url
        if any(x in purl for x in ('reader.elsevier.com', 'sciencedirectassets',
                                    'showpdf', 'pdfft', '/pdf/')):
            print(f"   [Elsevier] Found reader/PDF tab: {purl[:80]}")
            try:
                p.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            for dl_sel in [
                "a[href*='pdfft']",
                "a[href*='showPdf']",
                "button[aria-label='Download PDF']",
                "button[title='Download']",
                "button:has-text('Download')",
                "a:has-text('Download')",
                "#download-btn",
            ]:
                try:
                    p.click(dl_sel, timeout=5000)
                    print(f"   [Elsevier] Clicked reader download: {dl_sel}")
                    break
                except Exception:
                    continue


def _select_huji(page: Page) -> None:
    """Type HUJI into an institution search box and click the result."""
    dismiss_cookies(page)
    time.sleep(1)
    for sel in _INSTITUTION_INPUT_SELS:
        try:
            page.click(sel, timeout=3000)
            page.fill(sel, "")
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [Elsevier] Typed institution into: {sel}")
            try:
                page.wait_for_selector(
                    ", ".join(_INSTITUTION_RESULT_SELS), timeout=5000)
            except Exception:
                time.sleep(2)
            break
        except Exception:
            continue

    for sel in _INSTITUTION_RESULT_SELS:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Selected institution: {sel}")
            time.sleep(2)
            return
        except Exception:
            continue
    print("   [Elsevier] Could not find HUJI in results")


_HUJI_ENTITY_ID = "https://idp.huji.ac.il/idp/shibboleth"


def _build_sd_institution_login(article_url: str) -> str:
    """Build ScienceDirect institutional-login URL that forces Shibboleth redirect.

    Navigating here bypasses the need to find/click "Access through Hebrew
    University" buttons that are sometimes hidden or A/B-tested away.
    """
    from urllib.parse import quote
    return (
        "https://www.sciencedirect.com/user/institution/login"
        f"?entityID={quote(_HUJI_ENTITY_ID, safe='')}"
        f"&returnURL={quote(article_url, safe='')}"
    )


def authenticate_elsevier(page: Page, article_url: str, email: str, password: str,
                           captured: list, output_dir: str = None):
    """Elsevier/ScienceDirect auth flow."""
    print(f"\n[Elsevier Auth] Article: {article_url[:60]}")

    # If PDF was already captured during initial navigation (e.g. session cookies
    # caused ScienceDirect to redirect straight to the PDF), skip auth entirely.
    if captured:
        print("   [Elsevier] PDF already captured before auth — skipping")
        return

    # Navigate to the article page — Strategies 1-3 below handle auth from there.
    page.goto(article_url, wait_until="domcontentloaded", timeout=30_000)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    time.sleep(2)
    if detect_cloudflare_challenge(page):
        emit_cloudflare_alert(page)
        wait_for_cf_clear(page)

    # If the Chrome extension already captured the PDF (cached session), skip auth entirely
    if captured:
        print("   [Elsevier] PDF captured during navigation — skipping auth")
        return

    dismiss_cookies(page)
    time.sleep(1)

    current = page.url
    print(f"   [Elsevier] Landed on: {current[:80]}")

    # Screenshot immediately after initial load so we can see what the page shows
    import datetime as _dt0
    try:
        _ts0 = _dt0.datetime.now().strftime("%H%M%S")
        page.screenshot(path=f"debug_elsevier_landed_{_ts0}.png")
        print(f"   [Elsevier] Landing screenshot: debug_elsevier_landed_{_ts0}.png")
    except Exception:
        pass

    # ── Fast-path: check whether the PDF link is already accessible ───────────
    # If valid session cookies are present from a previous auth, the article page
    # loads with the institutional PDF download link already visible.  In that
    # case skip the entire auth flow (all three strategies + HUJI login) and jump
    # straight to the PDF download section below.  This avoids wasting 3-4 minutes
    # on selector timeouts that will never match.
    _pdf_accessible = False
    try:
        _pdf_accessible = bool(page.evaluate("""() =>
            !!document.querySelector(
                'a[href*="showPdf"], a[href*="pdfft"], a[href*="/doi/pdf"], '
                + 'a[href$=".pdf"]'
            )
        """))
        if _pdf_accessible:
            print("   [Elsevier] PDF link visible — session cookies valid, skipping auth flow")
    except Exception as _e:
        print(f"   [Elsevier] Fast-path check error: {_e}")

    # ── Strategy 1: click "Access through Hebrew University" if visible ────────
    # ScienceDirect article pages (e.g. /science/article/pii/...) show an
    # "Access through Hebrew University of Jeru..." button when the institution
    # is recognized.  This is the fastest auth path — click it first.
    if not _pdf_accessible and not any(d in page.url for d in _AUTH_DOMAINS):
        dismiss_cookies(page)
        time.sleep(1)
        dismiss_cookies(page)  # ScienceDirect often re-shows after JS loads
        time.sleep(0.5)

        for sel in [
            # Institutional access — MUST come before generic "Sign in"
            "a:has-text('Access through Hebrew University')",
            "button:has-text('Access through Hebrew University')",
            "a:has-text('Access through your institution')",
            "button:has-text('Access through your institution')",
            "a:has-text('Access through')",
            "button:has-text('Access through')",
            # Direct Shibboleth/HUJI links
            "a[href*='ShibAuth']",
            "a[href*='entityID=https%3A%2F%2Fidp.huji.ac.il']",
            "a[href*='entityID=https%3A%2F%2Fidp.cc.huji.ac.il']",
        ]:
            try:
                page.click(sel, timeout=3000)
                print(f"   [Elsevier] Clicked institutional access: {sel}")
                time.sleep(3)
                break
            except Exception:
                continue

    # ── Strategy 2: navigate to /fulltext (triggers auth redirect) ─────────────
    # On Elsevier journal platforms (ajog.org, thelancet.com), navigating
    # to /fulltext when unauthenticated triggers an auth redirect to
    # id.elsevier.com.  Works for /abstract URLs and also /science/article/pii.
    if not _pdf_accessible and not any(d in page.url for d in _AUTH_DOMAINS):
        fulltext_url = None
        if "/abstract" in current:
            fulltext_url = current.replace("/abstract", "/fulltext")
        elif "/science/article/pii/" in current:
            # ScienceDirect: append /fulltext to the pii URL
            fulltext_url = current.rstrip("/") + "?ref=pdf"
        if fulltext_url:
            print(f"   [Elsevier] Navigating to fulltext: {fulltext_url[:80]}")
            try:
                page.goto(fulltext_url, wait_until="domcontentloaded", timeout=15_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                time.sleep(2)
                if detect_cloudflare_challenge(page):
                    emit_cloudflare_alert(page)
                    wait_for_cf_clear(page)
                print(f"   [Elsevier] After fulltext nav: {page.url[:80]}")
            except Exception as e:
                print(f"   [Elsevier] Fulltext nav error (may be redirect): {e}")

    # ── Strategy 3: click sign-in / access buttons (last resort) ───────────────
    if not _pdf_accessible and not any(d in page.url for d in _AUTH_DOMAINS):
        import datetime as _dt
        _ts = _dt.datetime.now().strftime("%H%M%S")
        try:
            page.screenshot(path=f"debug_elsevier_{_ts}.png")
            print(f"   [Elsevier] Screenshot: debug_elsevier_{_ts}.png  (url={page.url[:80]})")
        except Exception:
            pass

        dismiss_cookies(page)
        time.sleep(0.5)

        # Wait for any access button to appear
        try:
            page.wait_for_selector(
                "button:has-text('Access'), a:has-text('Access'), "
                "button:has-text('Sign'), a:has-text('Sign'), "
                "button:has-text('Get access'), a:has-text('Get access')",
                timeout=6000,
            )
        except Exception:
            pass

        dismiss_cookies(page)
        time.sleep(0.5)

        for sel in [
            # Institutional access first (most reliable)
            "a:has-text('Log in via your institution')",
            "a:has-text('Institutional access')",
            "button:has-text('Get access')",
            "a:has-text('Get access')",
            "#access-options",
            "button.buybox__btn",
            # Generic sign-in (last resort — may go to Elsevier login)
            "button:has-text('Sign in')",
            "a:has-text('Sign in')",
            "[data-aa-button='signIn']",
            "a:has-text('Log in')",
            "button:has-text('Log in')",
        ]:
            try:
                page.click(sel, timeout=4000)
                print(f"   [Elsevier] Clicked: {sel}")
                time.sleep(2)
                break
            except Exception:
                continue

        # After clicking, look for institution link in any panel that opened
        if not any(d in page.url for d in _AUTH_DOMAINS):
            for sel in [
                "a:has-text('Access through Hebrew University')",
                "button:has-text('Access through Hebrew University')",
                "a:has-text('Access through your institution')",
                "button:has-text('Access through your institution')",
                "a:has-text('Access through')",
                "button:has-text('Access through')",
                "a:has-text('Log in via your institution')",
                "a:has-text('institution')",
                "a[href*='openathens']",
                "a[href*='shibboleth']",
                "a[href*='id.elsevier.com']",
            ]:
                try:
                    page.click(sel, timeout=4000)
                    print(f"   [Elsevier] Clicked institution link: {sel}")
                    time.sleep(3)
                    break
                except Exception:
                    continue

    if not _pdf_accessible:
        try:
            print(f"   [Elsevier] URL after click attempts: {page.url[:80]}")
        except Exception:
            print("   [Elsevier] Browser closed before auth could complete")
            return

        # ── Wait for auth/IdP page ─────────────────────────────────────────────
        try:
            page.wait_for_function(
                """() => {
                    const u = window.location.href;
                    return u.includes('id.elsevier.com') ||
                           u.includes('sciencedirect.com/user/ropc') ||
                           u.includes('wayfinder') ||
                           u.includes('openathens') ||
                           u.includes('huji.ac.il');
                }""",
                timeout=30_000,
            )
            current = page.url
            print(f"   [Elsevier] Auth page: {current[:80]}")

            if 'id.elsevier.com' in current or 'sciencedirect.com/user/ropc' in current:
                # Elsevier's own IdP — click "Continue with your institution" then search
                dismiss_cookies(page)
                for sel in [
                    "button:has-text('Continue with your institution')",
                    "a:has-text('Continue with your institution')",
                    "button:has-text('Access through your institution')",
                    "a:has-text('your institution')",
                    "button:has-text('your institution')",
                    "a[href*='institution']",
                ]:
                    try:
                        page.click(sel, timeout=4000)
                        print(f"   [Elsevier] Clicked IdP institution btn: {sel}")
                        time.sleep(3)
                        break
                    except Exception:
                        continue
                _select_huji(page)
                time.sleep(3)
                # If still on id.elsevier.com (HUJI not found in search results),
                # bypass the wayfinder entirely and navigate directly to the Shibboleth URL.
                if 'id.elsevier.com' in page.url or 'openathens' in page.url:
                    print("   [Elsevier] Institution select failed — using direct Shibboleth URL...")
                    shib_url = _build_sd_institution_login(article_url)
                    try:
                        page.goto(shib_url, wait_until="domcontentloaded", timeout=30_000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                        time.sleep(2)
                        if detect_cloudflare_challenge(page):
                            emit_cloudflare_alert(page)
                            wait_for_cf_clear(page)
                    except Exception as _e:
                        print(f"   [Elsevier] Shibboleth redirect error: {_e}")
            elif 'wayfinder' in current or 'openathens' in current:
                _select_huji(page)

        except Exception as e:
            print(f"   [Elsevier] Auth wait: {e}")

        wait_for_huji_and_login(page, email, password)

        print("\n[Elsevier] Waiting to return to journal...")
        try:
            page.wait_for_function(
                """() => {
                    const u = window.location.href;
                    return !u.includes('huji.ac.il') &&
                           !u.includes('openathens') &&
                           !u.includes('id.elsevier.com') &&
                           !u.includes('login');
                }""",
                timeout=90_000,
            )
            print(f"   Back: {page.url[:80]}")
        except Exception:
            print(f"   Timeout. URL: {page.url}")

        # After HUJI login, ScienceDirect may kick off a second OAuth2 round-trip
        # through id.elsevier.com before the final article page is ready.
        # Wait for ALL navigation to settle before touching the page.
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        time.sleep(2)
        if detect_cloudflare_challenge(page):
            emit_cloudflare_alert(page)
            wait_for_cf_clear(page)

        # Navigate to article — guard against being interrupted by OAuth callback
        try:
            page.goto(article_url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
        except Exception as e:
            print(f"   [Elsevier] Post-auth nav interrupted (OAuth in progress): {e}")
            # Just wait for whatever navigation is in flight to finish
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass

        time.sleep(2)

        # Reload the article page so the pdfft token is freshly minted for the
        # fully-established authenticated session (the post-OAuth state may not
        # yet have had a chance to write its own session cookies before page.goto).
        print("   Reloading to get fresh authenticated page...")
        try:
            page.reload(wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            time.sleep(2)
        except Exception as e:
            print(f"   [Elsevier] Reload error: {e}")

        # Check whether the PDF link is now accessible.  If the HUJI SSO completed
        # via a cached Elsevier session (no visit to huji.ac.il), the article page
        # may load without institutional access.  In that case force a fresh
        # Shibboleth-based login which bypasses all cached Elsevier sessions.
        _pdf_after_auth = False
        try:
            _pdf_after_auth = bool(page.evaluate("""() =>
                !!document.querySelector(
                    'a[href*="showPdf"], a[href*="pdfft"], a[href*="/doi/pdf"]'
                )
            """))
        except Exception:
            pass

        if not _pdf_after_auth and not captured:
            print("   [Elsevier] PDF link absent after auth — forcing fresh Shibboleth login...")
            shib_url = _build_sd_institution_login(article_url)
            try:
                page.goto(shib_url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                time.sleep(2)
                if detect_cloudflare_challenge(page):
                    emit_cloudflare_alert(page)
                    wait_for_cf_clear(page)
                wait_for_huji_and_login(page, email, password)
                try:
                    page.wait_for_function(
                        """() => {
                            const u = window.location.href;
                            return !u.includes('huji.ac.il') &&
                                   !u.includes('shibboleth') &&
                                   !u.includes('login');
                        }""",
                        timeout=90_000,
                    )
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass
                time.sleep(2)
                page.goto(article_url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                time.sleep(2)
                page.reload(wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                time.sleep(2)
            except Exception as _e:
                print(f"   [Elsevier] Re-auth error: {_e}")

    print(f"   Authenticated page: {page.title()[:80]}")

    from journal_club.pdf_capture import wait_for_pdf

    # ── PDF download ───────────────────────────────────────────────────────────
    # IMPORTANT: Do NOT open the PDF URL in a blank new tab via context.new_page()
    # + goto().  ScienceDirect's Cloudflare protection checks Referer, opener,
    # and sec-fetch-* headers.  A blank tab has none of these, causing Cloudflare
    # to redirect back to the article page without serving the PDF.
    #
    # Instead, click the PDF link element on the authenticated page.  This
    # preserves all headers and triggers a natural browser navigation.  If the
    # link opens a new tab (target="_blank"), pdf_capture's context.on("page")
    # handler auto-registers response/download hooks on it.

    print("\n[Elsevier] Downloading PDF from authenticated page...")

    import os as _os, tempfile as _tmp, json as _json
    from playwright.sync_api import TimeoutError as _PlaywrightTimeout

    # Give JavaScript time to render the PDF download button (AJOG / Elsevier pages
    # are heavily JS-driven and may not show the button until hydration completes).
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    time.sleep(2)

    # ── Strategy 1: Navigate to PDF URL via window.open ────────────────────────
    # Atypon/AJOG's "Download PDF" href (e.g. /action/showPdf?pii=...) is an
    # HTML page that uses JavaScript to redirect to the actual PDF URL.  If we
    # let Chrome handle this as a CDP file-download (via expect_download), it
    # saves the HTML page before JS can run, producing a non-PDF file.
    #
    # window.open() from the authenticated article page:
    #   • sets the opener + Referer so Cloudflare / anti-hotlink checks pass
    #   • runs JavaScript, so showPdf → pdfft redirect chains work
    #   • the pdf_capture response hook (registered via context.on("page"))
    #     captures the final PDF response, or the download hook saves it
    pdf_href = None
    try:
        pdf_href = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href]'));

            // Strategy 1: Prefer Elsevier/ScienceDirect domain links (article's own PDF)
            // These use showPdf, pdfft, /action/download, etc.
            const elsevier_pdf = links.find(a => {
                const h = (a.href || '').toLowerCase();
                const is_elsevier = h.includes('sciencedirect.com') ||
                                  h.includes('showpdf') ||
                                  h.includes('pdfft') ||
                                  h.includes('/action/download') ||
                                  h.includes('pdf.sciencedirectassets.com');
                const is_pdf = h.includes('pdf') || h.endsWith('.pdf');
                return is_elsevier && is_pdf;
            });
            if (elsevier_pdf) {
                console.log('[PDF] Found Elsevier domain PDF: ' + elsevier_pdf.href);
                return elsevier_pdf.href;
            }

            // Strategy 2: Prefer links with PDF text that are Elsevier endpoints
            const text_pdf = links.find(a => {
                const t = (a.innerText || a.textContent || '').toLowerCase();
                const h = (a.href || '').toLowerCase();
                const has_pdf_text = t.includes('pdf') || t.includes('download');
                const is_elsevier_endpoint = h.includes('showpdf') ||
                                           h.includes('pdfft') ||
                                           h.includes('sciencedirect') ||
                                           h.includes('/doi/pdf');
                return has_pdf_text && is_elsevier_endpoint;
            });
            if (text_pdf) {
                console.log('[PDF] Found PDF via text + Elsevier endpoint: ' + text_pdf.href);
                return text_pdf.href;
            }

            // Strategy 3: ANY PDF link on Elsevier domain (fallback)
            const any_elsevier = links.find(a => {
                const h = (a.href || '').toLowerCase();
                return (h.includes('sciencedirect.com') || h.includes('showpdf') ||
                       h.includes('pdfft') || h.includes('pdf.sciencedirectassets')) &&
                       (h.includes('pdf') || h.endsWith('.pdf'));
            });
            if (any_elsevier) {
                console.log('[PDF] Found any Elsevier PDF: ' + any_elsevier.href);
                return any_elsevier.href;
            }

            // Strategy 4: LAST RESORT - any PDF link (including external citations)
            const any_pdf = links.find(a => {
                const h = (a.href || '').toLowerCase();
                return h.includes('pdf') || h.endsWith('.pdf');
            });
            if (any_pdf) {
                console.log('[PDF] WARNING: Falling back to external PDF: ' + any_pdf.href);
                return any_pdf.href;
            }

            console.log('[PDF] No PDF link found');
            return null;
        }""")
    except Exception as e:
        print(f"   [Elsevier] DOM eval error: {e}")

    if pdf_href:
        print(f"   [Elsevier] PDF href: {pdf_href[:80]}")

        # ── Strategy A: click the actual link element on the page ─────────────
        # A real DOM click is a genuine user gesture — it bypasses Chrome's popup
        # blocker entirely and preserves the opener + Referer context that Elsevier
        # requires.  The route interceptor for **/showPdf** (registered in
        # pdf_capture.attach_pdf_hooks) captures the PDF bytes before Chrome's
        # viewer can consume them, so we never need to read the response via CDP.
        pdf_link_clicked = False
        for sel in [
            "a[href*='showPdf']",
            "a[href*='pdfft']",
            "a:has-text('Download PDF')",
            "button:has-text('Download PDF')",
            "a:has-text('PDF')",
            "button:has-text('PDF')",
        ]:
            try:
                page.click(sel, timeout=5000)
                print(f"   [Elsevier] Clicked PDF link: {sel}")
                pdf_link_clicked = True
                break
            except Exception:
                continue

        if not pdf_link_clicked:
            # ── Strategy B: window.open() — route interceptor still handles it ──
            # Use expect_popup() so we know whether Chrome actually opened the tab.
            from playwright.sync_api import TimeoutError as _PwTimeout
            try:
                with page.expect_popup(timeout=10_000) as _popup_info:
                    page.evaluate(f"window.open({_json.dumps(pdf_href)}, '_blank')")
                print("   [Elsevier] Popup opened via window.open")
            except _PwTimeout:
                print("   [Elsevier] window.open blocked/timed-out — route interceptor may still capture")

        if not captured:
            # First check immediately (after a brief settle) for any reader/PDF tabs
            # that opened when the link was clicked — don't wait 120s before looking.
            time.sleep(6)
            if not captured:
                _check_reader_tabs(page, captured)
            if not captured:
                wait_for_pdf(captured, timeout_s=60, output_dir=output_dir)
            if not captured:
                _check_reader_tabs(page, captured)
                wait_for_pdf(captured, timeout_s=30, output_dir=output_dir)
    else:
        # ── Strategy 2: no href found — try clicking PDF buttons ───────────────
        # Used for ScienceDirect articles where the PDF button may be a <button>
        # that opens a reader tab rather than triggering a direct download.
        # Do NOT use expect_download() — clicking "View PDF" opens reader.elsevier.com
        # (an HTML reader, not a PDF download), causing a 30s timeout with no event.
        print("   [Elsevier] No PDF href in DOM — trying button clicks...")

        _pdf_link_sels = [
            "a[href*='pdfft']",
            "a:has-text('View PDF')",
            "button:has-text('View PDF')",
            "a:has-text('Download PDF')",
            "button:has-text('Download PDF')",
            "a[href*='/pdf/']",
        ]

        clicked = False
        for sel in _pdf_link_sels:
            try:
                page.click(sel, timeout=5000)
                print(f"   [Elsevier] Clicked: {sel}")
                clicked = True
                break
            except Exception:
                continue

        if clicked and not captured:
            # Give the click a moment to open a tab or trigger a response
            time.sleep(6)
            _check_reader_tabs(page, captured)
            if not captured:
                wait_for_pdf(captured, timeout_s=60, output_dir=output_dir)
            if not captured:
                _check_reader_tabs(page, captured)
                wait_for_pdf(captured, timeout_s=30, output_dir=output_dir)
