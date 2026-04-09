# journal_club/auth_springer.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def authenticate_springer(page: Page, article_url: str, email: str, password: str,
                           captured: list):
    """SpringerNature subscription auth flow (used only if OA check failed)."""
    from urllib.parse import quote
    print(f"\n[Springer Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    dismiss_cookies(page)

    # Extract the institutional access href directly from the DOM
    # (avoids clicking the wrong "Log in" personal link)
    inst_url = page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a[href]'));
        const inst = links.find(a =>
            a.href.includes('wayf.springernature') ||
            (a.href.includes('openathens') && a.href.includes('redirect')) ||
            (a.innerText || a.textContent || '').trim() === 'Access through your institution'
        );
        return inst ? inst.href : null;
    }""")

    if inst_url:
        print(f"   [Springer] Navigating to institution access: {inst_url[:80]}")
        page.goto(inst_url, wait_until="domcontentloaded")
        time.sleep(3)
    else:
        # Fallback: build wayf URL from article URL
        encoded = quote(article_url, safe="")
        wayf_url = f"https://wayf.springernature.com/?redirect_uri={encoded}"
        print(f"   [Springer] No inst link found, navigating to wayf: {wayf_url[:80]}")
        page.goto(wayf_url, wait_until="domcontentloaded")
        time.sleep(3)

    print(f"   On: {page.url[:80]}")
    try:
        page.wait_for_function(
            """() => window.location.href.includes('wayfinder') ||
                     window.location.href.includes('openathens') ||
                     window.location.href.includes('wayf.springernature') ||
                     window.location.href.includes('huji.ac.il')""",
            timeout=30_000,
        )
        current = page.url
        print(f"   [Springer] Auth page: {current[:80]}")
        if any(x in current for x in ["wayfinder", "openathens", "wayf.springernature"]):
            dismiss_cookies(page)
            time.sleep(1)
            # Search for institution using the wayf search box
            for sel in ['#searchFormTextInput', 'input[name="search"]',
                        'input[placeholder*="nstitut"]', 'input[type="search"]',
                        'input.js-sa-institution-search', 'input[type="text"]']:
                try:
                    page.click(sel, timeout=3000)
                    page.type(sel, "Hebrew University of Jerusalem", delay=50)
                    print(f"   [Springer] Typed institution into: {sel}")
                    time.sleep(3)
                    break
                except Exception:
                    continue
            for sel in [
                "a:has-text('Hebrew University of Jerusalem')",
                "span:has-text('Hebrew University of Jerusalem')",
                "li:has-text('Hebrew University')",
                "a:has-text('Hebrew University')",
                "a.sa-institutionslink",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    print(f"   [Springer] Clicked institution: {sel}")
                    time.sleep(3)
                    break
                except Exception:
                    continue
    except Exception as e:
        print(f"   [Springer] Timeout: {e}")

    # Wait for HUJI IdP — may pass through sp.nature.com SAML relay first
    try:
        page.wait_for_function(
            "() => window.location.href.includes('huji.ac.il')",
            timeout=30_000,
        )
        time.sleep(1)
        from journal_club.huji_login import login_huji
        login_huji(page, email, password)
    except Exception as e:
        print(f"   [Springer] Did not reach HUJI: {e}")
    print("\n[Springer] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => !window.location.href.includes('huji.ac.il') &&
                     !window.location.href.includes('openathens') &&
                     !window.location.href.includes('wayf.springernature') &&
                     !window.location.href.includes('login')""",
            timeout=90_000,
        )
        print(f"   Back: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")
    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)

    # Extract direct PDF URL from authenticated DOM
    print("\n[Springer] Extracting PDF URL from authenticated page...")
    pdf_url = page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a[href]'));
        const pdf = links.find(a =>
            (a.href.endsWith('.pdf') || a.href.includes('/pdf')) &&
            (a.innerText || a.textContent || '').toLowerCase().includes('pdf')
        );
        return pdf ? pdf.href : null;
    }""")

    if pdf_url:
        print(f"   PDF URL: {pdf_url[:80]}")
        pdf_tab = page.context.new_page()
        pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
        from journal_club.pdf_capture import wait_for_pdf
        if not wait_for_pdf(captured, timeout_s=45):
            print("   [Springer] Chrome extension did not fire — retrying navigation...")
            pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
            wait_for_pdf(captured, timeout_s=30)
    else:
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
