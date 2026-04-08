# journal_club/auth_openathens.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def _click_access_through_institution(page: Page):
    for sel in [
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('Log in via your institution')",
        "a:has-text('Institutional access')",
        "a:has-text('Log in')",
        "button:has-text('Log in')",
        "[data-test='institution-login']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [OA Generic] Clicked: {sel}")
            time.sleep(3)
            return
        except Exception:
            continue
    print("   [OA Generic] No institution login button found")

def _select_huji_on_wayfinder(page: Page):
    dismiss_cookies(page)
    time.sleep(1)
    for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                'input[placeholder*="rganiz"]', 'input[name="org"]',
                'input[type="search"]', 'input[type="text"]']:
        try:
            page.click(sel, timeout=3000)
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [OA Generic] Typed institution: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue
    for sel in [
        "span:has-text('Hebrew University of Jerusalem')",
        "li:has-text('Hebrew University')",
        "[role='option']:has-text('Hebrew')",
        "a:has-text('Hebrew University')",
        "button:has-text('Hebrew University')",
        ".result:has-text('Hebrew')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [OA Generic] Selected institution: {sel}")
            time.sleep(2)
            return
        except Exception:
            continue
    print("   [OA Generic] Could not find institution result — may need manual selection")

def authenticate_openathens(page: Page, article_url: str, email: str, password: str,
                             captured: list):
    """Generic OpenAthens auth flow for NEJM, BMJ, OUP, Wiley, etc."""
    print(f"\n[OA Generic Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(2)
    dismiss_cookies(page)
    _click_access_through_institution(page)
    print(f"   On: {page.url[:80]}")
    try:
        page.wait_for_function(
            """() => window.location.href.includes('wayfinder') ||
                     window.location.href.includes('openathens') ||
                     window.location.href.includes('huji.ac.il')""",
            timeout=30_000,
        )
        current = page.url
        if "wayfinder" in current or "openathens" in current:
            _select_huji_on_wayfinder(page)
    except Exception as e:
        print(f"   [OA Generic] Timeout waiting for auth page: {e}")
    wait_for_huji_and_login(page, email, password)
    print("\n[OA Generic] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => {
                const url = window.location.href;
                return !url.includes('huji.ac.il') &&
                       !url.includes('openathens') &&
                       !url.includes('wayfinder') &&
                       !url.includes('login');
            }""",
            timeout=90_000,
        )
        print(f"   Back on journal: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")
    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    for sel in [
        "a:has-text('Download PDF')",
        "button:has-text('Download PDF')",
        "a:has-text('PDF')",
        "[aria-label*='PDF']",
        "a[href$='.pdf']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   Clicked: {sel}")
            break
        except Exception:
            continue
