"""
AJOG Auth Test — Phase 4
Real Chrome via CDP + response interception.
PDFs render inline (no download event) so we intercept the network response bytes.
"""

import subprocess
import time
import os
import sys
from playwright.sync_api import sync_playwright

ARTICLE_URL  = "https://www.ajog.org/article/S0002-9378(26)00179-1/abstract"
SHOW_PDF_URL = "https://www.ajog.org/action/showPdf?pii=S0002-9378%2826%2900179-1"
OUT_PDF      = "test_download.pdf"

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
    print("AJOG Auth Test — Real Chrome + Response Interception")
    print("=" * 60)

    chrome_path = find_chrome()
    if not chrome_path:
        print("❌ Chrome not found.")
        sys.exit(1)

    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-journal-test")
    os.makedirs(tmp_profile, exist_ok=True)

    print(f"\n[Step 1] Launching real Chrome...")
    proc = subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={tmp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        ARTICLE_URL
    ])
    time.sleep(3)

    with sync_playwright() as p:
        print("[Step 2] Connecting via CDP...")
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        print("   ✅ Connected")

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        pages = context.pages
        page = pages[0] if pages else context.new_page()

        try:
            page.click("button:has-text('Accept all cookies')", timeout=3000)
        except:
            pass

        print("\n[Step 3] Please log in via HUJI in the browser window.")
        print("   Click 'Get access' → 'Access through your institution'")
        print("   → Hebrew University → enter credentials → Enter")
        print("\n   Waiting up to 3 minutes...")

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
            print(f"\n   ✅ Auth done. URL: {page.url}")
        except:
            print(f"\n   ⚠ Timeout — proceeding. URL: {page.url}")

        # ── Step 4: Intercept PDF response ───────────────────────────────────
        print("\n[Step 4] Setting up PDF response interception...")
        pdf_captured = []

        def on_response(response):
            ct = response.headers.get("content-type", "")
            url = response.url
            if "pdf" in ct.lower() or "pdf" in url.lower():
                print(f"   → PDF response detected!")
                print(f"     URL: {url}")
                print(f"     Content-Type: {ct}")
                try:
                    body = response.body()
                    pdf_captured.append(body)
                    print(f"     Size: {len(body):,} bytes")
                except Exception as e:
                    print(f"     Could not read body: {e}")

        page.on("response", on_response)

        print("\n[Step 5] Navigating to PDF URL (response will be intercepted)...")
        try:
            page.goto(SHOW_PDF_URL, wait_until="commit", timeout=20_000)
            print(f"   → Navigated to: {page.url}")
        except Exception as e:
            print(f"   → Navigation note: {e}")

        # Wait a moment for response event to fire
        time.sleep(3)

        if not pdf_captured:
            # Try clicking the Download PDF button as fallback
            print("\n   → No PDF captured yet, trying Download PDF button...")
            try:
                # Go back to article first
                page.goto(ARTICLE_URL, wait_until="domcontentloaded")
                time.sleep(2)
                page.click("text=Download PDF", timeout=5000)
                time.sleep(3)
            except Exception as e:
                print(f"   → {e}")

        # ── Step 5: Save result ───────────────────────────────────────────────
        if pdf_captured:
            data = pdf_captured[0]
            # Verify it's actually a PDF
            if data[:4] == b'%PDF':
                with open(OUT_PDF, "wb") as f:
                    f.write(data)
                print(f"\n✅ SUCCESS — Real PDF saved ({len(data):,} bytes) → {OUT_PDF}")
                print("\n→ CONCLUSION: Electron's Chromium will work for AJOG PDF downloads.")
            else:
                print(f"\n⚠ Captured {len(data):,} bytes but doesn't start with %PDF")
                print(f"   First bytes: {data[:20]}")
                with open("captured_response.bin", "wb") as f:
                    f.write(data)
        else:
            print(f"\n❌ No PDF response intercepted.")
            print(f"   Current URL: {page.url}")
            # Check page content for clues
            content = page.content()
            if "_cf_chl" in content:
                print("   → Cloudflare challenge appeared")
            elif "paywall" in content.lower() or "subscribe" in content.lower():
                print("   → Paywall detected — auth session may have expired")
            else:
                print("   → Unknown issue. Saving page content...")
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(content[:5000])

        input("\nPress Enter to close Chrome...")
        browser.close()
        proc.terminate()

    print("=" * 60)

if __name__ == "__main__":
    run()
