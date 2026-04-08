"""
AJOG Auth Test — Phase 3
Uses the user's REAL installed Chrome browser (not Playwright's Chromium).
Real Chrome passes Cloudflare because it has genuine browser fingerprinting.
If this works → Electron's Chromium will also work (same principle).

HOW TO RUN:
1. Close all Chrome windows first
2. Run this script — it will launch Chrome for you
3. Log in to AJOG via HUJI when the browser opens
4. Script intercepts the PDF download
"""

import subprocess
import time
import os
import sys
from playwright.sync_api import sync_playwright

ARTICLE_URL = "https://www.ajog.org/article/S0002-9378(26)00179-1/abstract"
OUT_PDF     = "test_download.pdf"

# Common Chrome paths on Windows
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

def find_chrome():
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None

def run():
    print("=" * 60)
    print("AJOG Auth Test — Real Chrome via CDP")
    print("=" * 60)

    chrome_path = find_chrome()
    if not chrome_path:
        print("❌ Chrome not found. Please install Chrome or update CHROME_PATHS.")
        sys.exit(1)

    print(f"\n[Step 1] Launching your real Chrome with debugging port...")
    print(f"   → {chrome_path}")

    # Temp profile so we don't affect your real Chrome profile
    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-journal-test")
    os.makedirs(tmp_profile, exist_ok=True)

    proc = subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={tmp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        ARTICLE_URL
    ])
    print("   → Chrome launched (temp profile, won't affect your normal Chrome)")
    print("   → Waiting for Chrome to start...")
    time.sleep(3)

    with sync_playwright() as p:
        print("\n[Step 2] Connecting to your Chrome via CDP...")
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("   ✅ Connected to real Chrome")
        except Exception as e:
            print(f"   ❌ Could not connect: {e}")
            proc.terminate()
            return

        context = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
        pages = context.pages
        page = pages[0] if pages else context.new_page()

        # Accept cookies if banner appears
        try:
            page.click("button:has-text('Accept all cookies')", timeout=4000)
            print("\n   → Cookie banner dismissed")
        except:
            pass

        print("\n[Step 3] Please complete the HUJI login in the browser window:")
        print("   1. Click 'Get access' or 'Download PDF'")
        print("   2. Click 'Access through your institution'")
        print("   3. Type 'Hebrew University' and select it")
        print("   4. Enter your HUJI email + password → Enter")
        print("\n   Waiting up to 3 minutes for auth to complete...")

        try:
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
            print(f"\n   ⚠ Timeout — proceeding anyway. URL: {page.url}")

        print("\n[Step 4] Attempting PDF download via real Chrome (Cloudflare test)...")

        # Enable downloads on this context
        try:
            context = page.context
            # For CDP-connected contexts, set download path
        except:
            pass

        try:
            with page.expect_download(timeout=40_000) as dl_info:
                print("   → Clicking Download PDF...")
                try:
                    page.click("a[href*='pdf']:visible", timeout=5000)
                except:
                    try:
                        page.click("text=Download PDF", timeout=5000)
                    except:
                        print("   → Could not find button — please click 'Download PDF' manually in the browser")

            download = dl_info.value
            download.save_as(OUT_PDF)
            size = os.path.getsize(OUT_PDF)
            print(f"\n✅ SUCCESS — PDF downloaded via real Chrome! ({size:,} bytes) → {OUT_PDF}")
            print("\n→ CONCLUSION: Electron's Chromium will work. Architecture confirmed.")

        except Exception as e:
            print(f"\n❌ Download failed: {e}")
            print("\n→ Let's check what Cloudflare did...")
            # Check if Cloudflare challenge appeared
            content = page.content()
            if "_cf_chl" in content or "Just a moment" in content:
                print("   Cloudflare challenge appeared even in real Chrome.")
                print("   This means Elsevier may block all automation on PDF URLs.")
            else:
                print(f"   Current URL: {page.url}")
                print("   No Cloudflare challenge detected — different error.")

        input("\nPress Enter to close Chrome...")
        browser.close()
        proc.terminate()

    print("\n" + "=" * 60)

if __name__ == "__main__":
    run()
