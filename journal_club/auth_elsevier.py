# journal_club/auth_elsevier.py
import time
from playwright.sync_api import Page

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


def authenticate_elsevier(page: Page, article_url: str, email: str, password: str,
                           captured: list):
    """Elsevier/ScienceDirect auth flow."""
    print(f"\n[Elsevier Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    time.sleep(2)

    # If the Chrome extension already captured the PDF (cached session), skip auth entirely
    if captured:
        print("   [Elsevier] PDF captured during navigation — skipping auth")
        return

    dismiss_cookies(page)
    time.sleep(1)

    current = page.url
    print(f"   [Elsevier] Landed on: {current[:80]}")

    # ── Strategy 1: click "Access through Hebrew University" if visible ────────
    # ScienceDirect article pages (e.g. /science/article/pii/...) show an
    # "Access through Hebrew University of Jeru..." button when the institution
    # is recognized.  This is the fastest auth path — click it first.
    if not any(d in page.url for d in _AUTH_DOMAINS):
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
    if not any(d in page.url for d in _AUTH_DOMAINS):
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
                print(f"   [Elsevier] After fulltext nav: {page.url[:80]}")
            except Exception as e:
                print(f"   [Elsevier] Fulltext nav error (may be redirect): {e}")

    # ── Strategy 3: click sign-in / access buttons (last resort) ───────────────
    if not any(d in page.url for d in _AUTH_DOMAINS):
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

    print(f"   [Elsevier] URL after click attempts: {page.url[:80]}")

    # ── Wait for auth/IdP page ─────────────────────────────────────────────────
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

    # Navigate to article — guard against being interrupted by OAuth callback
    try:
        page.goto(article_url, wait_until="domcontentloaded")
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

    # Try clicking the PDF link element directly (most reliable)
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
            print(f"   [Elsevier] Clicked PDF link: {sel}")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        # Fallback: extract URL from DOM and open via window.open (preserves opener)
        print("   [Elsevier] No clickable PDF link — extracting URL from DOM...")
        try:
            pdf_url = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                const pdf = links.find(a =>
                    (a.href.includes('pdfft') || a.href.includes('/pdf/') ||
                     a.href.endsWith('.pdf') || a.href.includes('pdf.sciencedirect')) &&
                    (a.innerText || a.textContent || '').toLowerCase().includes('pdf')
                );
                return pdf ? pdf.href : null;
            }""")
        except Exception:
            pdf_url = None

        if pdf_url:
            print(f"   [Elsevier] Opening via window.open: {pdf_url[:80]}")
            page.evaluate(f"window.open('{pdf_url}', '_blank')")
            clicked = True
        else:
            print("   [Elsevier] No PDF URL found in DOM")

    if clicked:
        # Wait for PDF capture from response/download hooks
        # (hooks auto-registered on new tabs via context.on("page") in pdf_capture)
        if not wait_for_pdf(captured, timeout_s=60):
            # If the ScienceDirect Reader opened, try its download button
            print("   [Elsevier] PDF not captured yet — checking for Reader page...")
            for p in page.context.pages:
                if p == page:
                    continue
                purl = p.url
                if any(x in purl for x in ('reader.elsevier.com', 'sciencedirectassets', 'pdf')):
                    print(f"   [Elsevier] Found PDF/Reader page: {purl[:80]}")
                    for dl_sel in [
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
                    break
            wait_for_pdf(captured, timeout_s=30)
