"""
AJOG Auth Test — Phase 2
Approach: Real browser for auth → captured cookies → plain HTTP for PDF download.
This simulates exactly what the Electron desktop app will do.

Steps:
1. Opens a visible Chromium window on the article page
2. You log in through your institution normally
3. Script detects when you're back on AJOG with access
4. Captures session cookies
5. Downloads PDF using those cookies via plain HTTP (no browser needed)
6. Reports result
"""

import httpx
import json
from playwright.sync_api import sync_playwright

ARTICLE_URL = "https://www.ajog.org/article/S0002-9378(26)00179-1/abstract"
PDF_URL     = "https://www.ajog.org/article/S0002-9378(26)00179-1/pdf"
OUT_PDF     = "test_download.pdf"

def is_authenticated(page) -> bool:
    """Check if we're back on AJOG with an active session."""
    url = page.url
    return "ajog.org" in url and "idp" not in url and "openathens" not in url and "login" not in url

def run():
    print("=" * 60)
    print("AJOG / HUJI — WebView Auth + HTTP Download Test")
    print("=" * 60)

    with sync_playwright() as p:
        # Launch visible browser (not headless)
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context()
        page = context.new_page()

        # ── Step 1: Navigate to article ──────────────────────────────────────
        print("\n[Step 1] Opening article in browser window...")
        print(f"   → {ARTICLE_URL}")
        page.goto(ARTICLE_URL, wait_until="domcontentloaded")

        # Accept cookies if banner appears
        try:
            page.click("button:has-text('Accept all cookies')", timeout=3000)
            print("   → Cookie banner dismissed")
        except:
            pass

        # ── Step 2: Click 'Get Access' / PDF button ──────────────────────────
        print("\n[Step 2] Looking for access/PDF button to trigger auth flow...")
        try:
            # Try clicking the PDF button in the toolbar
            page.click("text=Download PDF", timeout=5000)
            print("   → Clicked 'Download PDF'")
        except:
            try:
                page.click("text=Get access", timeout=3000)
                print("   → Clicked 'Get access'")
            except:
                print("   → Could not find button — please click 'Get access' or 'Download PDF' manually")

        # ── Step 3: Wait for user to complete HUJI login ─────────────────────
        print("\n[Step 3] Waiting for you to complete login...")
        print("   → Please:")
        print("      1. Click 'Access through your institution'")
        print("      2. Type 'Hebrew University' and select it")
        print("      3. Enter your HUJI email + password")
        print("      4. Click Enter")
        print("\n   Waiting up to 3 minutes...")

        try:
            # Wait until we're back on AJOG (not on login/OpenAthens pages)
            page.wait_for_function(
                """() => {
                    const url = window.location.href;
                    return url.includes('ajog.org') &&
                           !url.includes('idp') &&
                           !url.includes('openathens') &&
                           !url.includes('login');
                }""",
                timeout=180_000
            )
            print(f"\n   ✅ Auth complete! Back on: {page.url}")
        except Exception as e:
            print(f"\n   ⚠ Timed out or error: {e}")
            print(f"   Current URL: {page.url}")

        # ── Step 4: Capture session cookies ──────────────────────────────────
        print("\n[Step 4] Capturing session cookies...")
        cookies = context.cookies()
        ajog_cookies = [c for c in cookies if "ajog" in c["domain"] or "elsevier" in c["domain"] or "healthadvance" in c["domain"]]
        print(f"   → Captured {len(ajog_cookies)} AJOG/Elsevier cookies")
        for c in ajog_cookies:
            print(f"      {c['name']}: {c['value'][:40]}...")

        # Save cookies to file for inspection
        with open("captured_cookies.json", "w") as f:
            json.dump(ajog_cookies, f, indent=2)
        print("   → Saved to captured_cookies.json")

        browser.close()

    # ── Step 5: Download PDF directly via browser (bypasses Cloudflare) ──────
    print("\n[Step 5] Downloading PDF via browser (intercepts download)...")
    print("   → Cloudflare requires a real browser — plain HTTP won't work")
    print("   → Using browser download interception instead")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(accept_downloads=True)

        # Restore session cookies from previous auth
        context.add_cookies(ajog_cookies)
        page = context.new_page()

        print(f"   → Navigating to article (with auth cookies)...")
        page.goto(ARTICLE_URL, wait_until="domcontentloaded")
        print(f"   → Page title: {page.title()}")

        # Intercept the PDF download
        print("   → Clicking 'Download PDF' and intercepting file...")
        try:
            with page.expect_download(timeout=30_000) as dl_info:
                # Try bottom toolbar PDF button
                try:
                    page.click("a[href*='/pdf']:visible", timeout=5000)
                except:
                    page.click("text=Download PDF", timeout=5000)

            download = dl_info.value
            download.save_as(OUT_PDF)
            size = download.path() and __import__('os').path.getsize(OUT_PDF)
            print(f"\n✅ SUCCESS — PDF downloaded via browser ({size:,} bytes) → {OUT_PDF}")

        except Exception as e:
            print(f"\n   Download intercept failed: {e}")
            print("   → Trying showPdf URL directly...")
            show_pdf_url = f"https://www.ajog.org/action/showPdf?pii=S0002-9378%2826%2900179-1"
            try:
                with page.expect_download(timeout=20_000) as dl_info:
                    page.goto(show_pdf_url)
                download = dl_info.value
                download.save_as(OUT_PDF)
                size = __import__('os').path.getsize(OUT_PDF)
                print(f"\n✅ SUCCESS — PDF downloaded via showPdf ({size:,} bytes) → {OUT_PDF}")
            except Exception as e2:
                # Maybe it renders inline — check content
                r_check = page.goto(show_pdf_url)
                ct = r_check.headers.get("content-type", "") if r_check else ""
                print(f"   Content-Type: {ct}")
                if "pdf" in ct:
                    content = page.content()
                    print(f"✅ PDF rendered inline in browser (content-type: {ct})")
                else:
                    print(f"❌ Could not download PDF: {e2}")

        browser.close()

    print("\n" + "=" * 60)

if __name__ == "__main__":
    run()
