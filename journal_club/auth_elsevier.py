# journal_club/auth_elsevier.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def authenticate_elsevier(page: Page, article_url: str, email: str, password: str,
                           captured: list):
    """Elsevier/ScienceDirect auth flow."""
    print(f"\n[Elsevier Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    dismiss_cookies(page)
    for sel in [
        "text=Get access",
        "button:has-text('Get access')",
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('Institutional access')",
        "#access-options",
        "button.buybox__btn",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue
    for sel in [
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('institution')",
        "a[href*='openathens']",
        "a[href*='shibboleth']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked institution link: {sel}")
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
        current = page.url
        if "wayfinder" in current or "openathens" in current:
            dismiss_cookies(page)
            time.sleep(1)
            for sel in ['input[placeholder*="nstitut"]', 'input[type="search"]', 'input[type="text"]']:
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
                "[role='option']:has-text('Hebrew')",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    time.sleep(2)
                    break
                except Exception:
                    continue
    except Exception as e:
        print(f"   [Elsevier] Timeout: {e}")
    wait_for_huji_and_login(page, email, password)
    print("\n[Elsevier] Waiting to return to journal...")
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
        "a[href*='pdfft']",
        "a[href$='.pdf']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked: {sel}")
            break
        except Exception:
            continue
