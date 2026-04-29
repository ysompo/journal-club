# journal_club/huji_login.py
import time
from playwright.sync_api import Page

def dismiss_cookies(page: Page, timeout_ms: int = 3000):
    """Try common cookie banner dismiss buttons, including JS fallback for shadow DOM."""
    # JavaScript fallback — handles OneTrust in both simple-banner and preference-center states.
    # onetrust-pc-btn-handler has dual meaning:
    #   • On simple banner  → opens the preference center  (DO NOT click)
    #   • Inside preference center → "Confirm my choices"  (click to dismiss)
    # So: if preference center is visible, click pc-btn-handler; otherwise click accept-btn-handler.
    try:
        clicked = page.evaluate("""() => {
            const pcSdk = document.getElementById('onetrust-pc-sdk');
            const pcVisible = pcSdk && getComputedStyle(pcSdk).display !== 'none';

            if (pcVisible) {
                // Preference center is open — "Confirm my choices"
                const btn = document.getElementById('onetrust-pc-btn-handler');
                if (btn) { btn.click(); return 'pc-confirm'; }
            }

            // Simple banner — "Accept All"
            const acceptBtn = document.getElementById('onetrust-accept-btn-handler');
            if (acceptBtn) { acceptBtn.click(); return 'accept-all'; }

            // Generic text fallback
            const btns = Array.from(document.querySelectorAll('button'));
            const target = btns.find(b =>
                /accept all|allow all|confirm my choices/i.test(b.textContent)
            );
            if (target) { target.click(); return 'text-match'; }
            return false;
        }""")
        if clicked:
            time.sleep(0.5)
            return
    except Exception:
        pass

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
    Assumes page is already on the HUJI IdP (idp.cc.huji.ac.il or idp.huji.ac.il).
    Handles both the old CC IdP (email-tab flow) and the new Keycloak-based IdP.
    Falls back to manual wait if selectors fail.
    """
    print(f"   [HUJI] On: {page.url[:60]}")

    # Wait for a visible form field — Keycloak pages may still be loading
    for sel in ['#username', 'input[name="username"]', 'input[type="email"]',
                'input[name="j_username"]']:
        try:
            page.wait_for_selector(sel, state="visible", timeout=8000)
            break
        except Exception:
            continue

    # Click "With E-mail password" tab (old CC IdP only — silently skip on Keycloak)
    for sel in [
        "text=With E-mail password",
        "button:has-text('E-mail password')",
        "a:has-text('E-mail password')",
        "[role='tab']:has-text('E-mail')",
    ]:
        try:
            page.click(sel, timeout=3000)
            print("   [HUJI] Clicked email tab")
            time.sleep(1)
            break
        except Exception:
            continue

    # Fill username / email
    # Keycloak uses id="username" (text type), old CC IdP uses input[type="email"]
    for sel in ['#username', 'input[name="username"]', 'input[name="j_username"]',
                'input[type="email"]', 'input[placeholder*="user"]',
                'input[placeholder*="mail"]']:
        try:
            existing = page.input_value(sel, timeout=3000)
            if not existing:
                page.fill(sel, email, timeout=3000)
            print(f"   [HUJI] Username/email ready ({sel})")
            break
        except Exception:
            continue

    # Fill password
    for sel in ['#password', 'input[name="password"]', 'input[name="j_password"]',
                'input[type="password"]']:
        try:
            page.fill(sel, password, timeout=3000)
            print(f"   [HUJI] Password filled ({sel})")
            break
        except Exception:
            continue

    # Submit — Keycloak uses id="kc-login"; old CC IdP uses type="submit"
    for sel in ['#kc-login', 'button:has-text("Sign In")', 'button:has-text("Sign in")',
                'button:has-text("Login")', 'button:has-text("Enter")',
                'button[type="submit"]', 'input[type="submit"]',
                'button:has-text("Log in")']:
        try:
            page.click(sel, timeout=3000)
            print(f"   [HUJI] Submitted ({sel})")
            return
        except Exception:
            continue

    print(f"   [HUJI] Auto-submit failed — waiting {manual_timeout_s}s for manual login")
    time.sleep(manual_timeout_s)


def wait_for_huji_and_login(page: Page, email: str, password: str,
                             arrive_timeout_ms: int = 60_000):
    """
    Wait for page to navigate to huji.ac.il, then call login_huji().
    """
    try:
        page.wait_for_function(
            "() => window.location.href.includes('huji.ac.il')",
            timeout=arrive_timeout_ms,
        )
        # Let any post-redirect page settle before trying to fill the form
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        time.sleep(2)
        login_huji(page, email, password)
    except Exception as e:
        print(f"   [HUJI] Did not reach HUJI login: {e}")
        # Don't sleep 20s here — if we're already authenticated via cookies the
        # HUJI page never appears and we'd waste 20 seconds on every download.
        time.sleep(2)
