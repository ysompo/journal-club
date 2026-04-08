# journal_club/auth_jama.py
import time
from urllib.parse import quote
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def _build_shibboleth_url(article_url: str) -> str:
    """Return the JAMA Shibboleth login URL that redirects back to the given article."""
    return_url = article_url.replace("article-abstract", "fullarticle")
    encoded = quote(return_url, safe="")
    return f"https://jamanetwork.com/signinshibboleth?returnUrl={encoded}"

def _select_huji_on_jama(page: Page):
    """Type Hebrew University in the JAMA institution search and click the result."""
    print("   [JAMA] Selecting HUJI institution...")
    page.click("input.js-sa-institution-search", timeout=10_000)
    page.type("input.js-sa-institution-search", "Hebrew University", delay=50)
    time.sleep(3)
    page.click("a.sa-institutionslink", timeout=10_000)
    print("   [JAMA] Selected Hebrew University of Jerusalem")
    time.sleep(2)
    print(f"   [JAMA] On: {page.url[:80]}")

def _handle_openathens_intermediate(page: Page):
    """
    If page lands on login.openathens.net, dismiss cookies, search for HUJI, click result.
    """
    if "openathens" not in page.url:
        return
    print("   [JAMA] OpenAthens intermediate detected")
    dismiss_cookies(page)
    time.sleep(1)

    for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                'input[placeholder*="rganiz"]', 'input[name="institution"]',
                'input[type="search"]', 'input[type="text"]']:
        try:
            page.click(sel, timeout=3000)
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [JAMA/OA] Typed institution: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

    for sel in [
        "li:has-text('Hebrew University')",
        "[role='option']:has-text('Hebrew')",
        "a:has-text('Hebrew University')",
        "button:has-text('Hebrew University')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [JAMA/OA] Clicked institution result: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

def authenticate_jama(page: Page, article_url: str, email: str, password: str,
                      captured: list):
    """Full JAMA auth flow. Assumes PDF hooks already attached to page/context."""
    shib_url = _build_shibboleth_url(article_url)
    print(f"\n[JAMA Auth] Navigating to Shibboleth URL...")
    page.goto(shib_url, wait_until="domcontentloaded")
    time.sleep(2)
    print(f"   On: {page.url[:80]}")

    _select_huji_on_jama(page)

    # May land on OpenAthens intermediate before HUJI
    try:
        page.wait_for_function(
            "() => window.location.href.includes('huji.ac.il') || window.location.href.includes('openathens')",
            timeout=30_000,
        )
        _handle_openathens_intermediate(page)
    except Exception as e:
        print(f"   [JAMA Auth] Timeout waiting for HUJI/OA: {e}")

    wait_for_huji_and_login(page, email, password)

    # Wait to return to JAMA
    print("\n[JAMA Auth] Waiting to return to JAMA...")
    try:
        page.wait_for_function(
            """() => window.location.href.includes('jamanetwork.com') &&
                     !window.location.href.includes('login') &&
                     !window.location.href.includes('idp')""",
            timeout=90_000,
        )
        print(f"   Back on JAMA: {page.url}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)

    # Navigate to fulltext page
    ft_url = article_url.replace("article-abstract", "fullarticle")
    page.goto(ft_url, wait_until="domcontentloaded")
    time.sleep(3)

    # Click Download PDF
    print("\n[JAMA Auth] Clicking Download PDF...")
    for sel in [
        "a:has-text('Download PDF')",
        "button:has-text('Download PDF')",
        "[aria-label*='Download PDF']",
        "a[data-article-action='download-pdf']",
        ".article-tools__item--pdf a",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   Clicked: {sel}")
            break
        except Exception:
            continue
