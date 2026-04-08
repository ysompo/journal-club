# journal_club/auth_springer.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def authenticate_springer(page: Page, article_url: str, email: str, password: str,
                           captured: list):
    """SpringerNature subscription auth flow (used only if OA check failed)."""
    print(f"\n[Springer Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    dismiss_cookies(page)
    for sel in [
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('Log in via your institution')",
        "a:has-text('Log in')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Springer] Clicked: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue
    for sel in [
        "a:has-text('Access through your institution')",
        "a:has-text('institution')",
        "a:has-text('Shibboleth')",
        "a:has-text('OpenAthens')",
        "[data-test='institution-login']",
    ]:
        try:
            page.click(sel, timeout=3000)
            print(f"   [Springer] Gateway click: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue
    print(f"   On: {page.url[:80]}")
    try:
        page.wait_for_function(
            """() => window.location.href.includes('wayfinder') ||
                     window.location.href.includes('openathens') ||
                     window.location.href.includes('huji.ac.il')""",
            timeout=30_000,
        )
        if "wayfinder" in page.url or "openathens" in page.url:
            dismiss_cookies(page)
            time.sleep(1)
            for sel in ['input[placeholder*="nstitut"]', 'input[type="search"]',
                        'input.js-sa-institution-search', 'input[type="text"]']:
                try:
                    page.click(sel, timeout=3000)
                    page.type(sel, "Hebrew University of Jerusalem", delay=50)
                    time.sleep(2)
                    break
                except Exception:
                    continue
            for sel in [
                "span:has-text('Hebrew University of Jerusalem')",
                "li:has-text('Hebrew University')",
                "a:has-text('Hebrew University')",
                "a.sa-institutionslink",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    time.sleep(2)
                    break
                except Exception:
                    continue
    except Exception as e:
        print(f"   [Springer] Timeout: {e}")
    wait_for_huji_and_login(page, email, password)
    print("\n[Springer] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => !window.location.href.includes('huji.ac.il') &&
                     !window.location.href.includes('openathens') &&
                     !window.location.href.includes('login')""",
            timeout=90_000,
        )
        print(f"   Back: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")
    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    for sel in [
        "a:has-text('Download PDF')",
        "button:has-text('Download PDF')",
        "a[href$='.pdf']",
        "a:has-text('PDF')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Springer] Clicked: {sel}")
            break
        except Exception:
            continue
