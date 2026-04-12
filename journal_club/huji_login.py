# journal_club/huji_login.py
import time
from playwright.sync_api import Page

def dismiss_cookies(page: Page, timeout_ms: int = 3000):
    """Try common cookie banner dismiss buttons."""
    for sel in [
        "button:has-text('Accept all cookies')",
        "button:has-text('Accept all')",
        "button:has-text('Allow all')",
        "button:has-text('Accept necessary cookies')",
        "button:has-text('Confirm my choices')",   # OneTrust preference center (Elsevier/AJOG)
        "button#onetrust-accept-btn-handler",       # OneTrust standard accept button
        "button.onetrust-close-btn-handler",        # OneTrust close
        "button:has-text('Accept')",
        "button:has-text('I agree')",
        "button:has-text('OK')",
    ]:
        try:
            page.click(sel, timeout=timeout_ms)
            time.sleep(0.5)
            return
        except Exception:
            continue


def login_huji(page: Page, email: str, password: str, manual_timeout_s: int = 20):
    """
    Assumes page is already on the HUJI IdP (idp.cc.huji.ac.il).
    Clicks the "With E-mail password" tab, fills credentials, submits.
    Falls back to manual wait if selectors fail.
    """
    print(f"   [HUJI] On: {page.url[:60]}")

    # Click "With E-mail password" tab
    for sel in [
        "text=With E-mail password",
        "button:has-text('E-mail password')",
        "a:has-text('E-mail password')",
        "[role='tab']:has-text('E-mail')",
    ]:
        try:
            page.click(sel, timeout=4000)
            print("   [HUJI] Clicked email tab")
            time.sleep(1)
            break
        except Exception:
            continue

    # Fill email
    for sel in ['input[type="email"]', 'input[name="username"]', '#username',
                'input[placeholder*="mail"]']:
        try:
            existing = page.input_value(sel)
            if not existing:
                page.fill(sel, email, timeout=3000)
            print(f"   [HUJI] Email ready")
            break
        except Exception:
            continue

    # Fill password
    for sel in ['input[type="password"]', 'input[name="password"]', '#password']:
        try:
            page.fill(sel, password, timeout=3000)
            print(f"   [HUJI] Password filled")
            break
        except Exception:
            continue

    # Submit
    for sel in ['button:has-text("Enter")', 'button[type="submit"]',
                'input[type="submit"]', 'button:has-text("Log in")']:
        try:
            page.click(sel, timeout=3000)
            print(f"   [HUJI] Submitted")
            return
        except Exception:
            continue

    print(f"   [HUJI] Auto-submit failed — waiting {manual_timeout_s}s for manual login")
    time.sleep(manual_timeout_s)


def wait_for_huji_and_login(page: Page, email: str, password: str,
                             arrive_timeout_ms: int = 30_000):
    """
    Wait for page to navigate to huji.ac.il, then call login_huji().
    """
    try:
        page.wait_for_function(
            "() => window.location.href.includes('huji.ac.il')",
            timeout=arrive_timeout_ms,
        )
        time.sleep(1)
        login_huji(page, email, password)
    except Exception as e:
        print(f"   [HUJI] Did not reach HUJI login: {e}")
        time.sleep(20)
