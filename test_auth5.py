"""
AJOG Auth Test — Phase 5
- Auth + download in a single Chrome session (no session expiry)
- Intercepts ALL network responses to catch CDN redirect destination
- showPdf redirects to a CDN URL (likely sciencedirectassets.com) — we catch that
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
    print("AJOG Auth Test — Single Session + CDN Intercept")
    print("=" * 60)

    chrome_path = find_chrome()
    if not chrome_path:
        print("❌ Chrome not found.")
        sys.exit(1)

    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-journal-test2")
    os.makedirs(tmp_profile, exist_ok=True)

    print(f"\n[Step 1] Launching Chrome...")
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
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        pages = context.pages
        page = pages[0] if pages else context.new_page()

        try:
            page.click("button:has-text('Accept all cookies')", timeout=3000)
        except:
            pass

        # ── Step 2: Auth ──────────────────────────────────────────────────────
        print("\n[Step 2] Please log in via HUJI:")
        print("   Click 'Get access' → 'Access through your institution'")
        print("   → Hebrew University → credentials → Enter")
        print("   Waiting up to 3 minutes...")

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
            print(f"   ✅ Auth done. URL: {page.url}")
        except:
            print(f"   ⚠ Timeout. URL: {page.url}")

        # ── Step 3: Intercept ALL responses to find PDF ───────────────────────
        print("\n[Step 3] Setting up full response interception...")
        print("   (Catching all responses — CDN URLs, asset URLs, everything)")

        pdf_captured = []
        all_responses = []

        def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            status = response.status

            # Log everything non-trivial
            if status not in (204,) and not any(x in url for x in [
                "google", "analytics", "doubleclick", "nr-data", "cloudflare",
                "fonts", "svg", "png", "jpg", "css", "woff", "tracking"
            ]):
                all_responses.append((status, ct, url))

            # Capture PDF responses
            if "pdf" in ct.lower() or (
                "application/octet-stream" in ct.lower() and "pdf" in url.lower()
            ) or "sciencedirectassets" in url:
                print(f"\n   → Potential PDF response:")
                print(f"     Status: {status} | CT: {ct}")
                print(f"     URL: {url[:100]}")
                if status == 200 and not pdf_captured:
                    try:
                        body = response.body()
                        if body[:4] == b'%PDF':
                            print(f"     ✅ Valid PDF! ({len(body):,} bytes)")
                            pdf_captured.append(body)
                        else:
                            print(f"     ⚠ Not a PDF (starts with: {body[:10]})")
                    except Exception as e:
                        print(f"     Could not read body: {e}")

        page.on("response", on_response)

        # ── Step 4: Open showPdf in a new tab ────────────────────────────────
        print(f"\n[Step 4] Opening PDF URL in new tab...")
        pdf_page = context.new_page()
        pdf_page.on("response", on_response)

        try:
            pdf_page.goto(SHOW_PDF_URL, wait_until="commit", timeout=20_000)
            print(f"   → Landed on: {pdf_page.url}")
            time.sleep(4)  # Wait for CDN response to come through
        except Exception as e:
            print(f"   → Note: {e}")

        # ── Step 5: Also try navigating to the final PDF CDN URL if we saw it ─
        if not pdf_captured:
            print("\n[Step 5] Checking all intercepted responses for clues...")
            print(f"   Total responses captured: {len(all_responses)}")
            for status, ct, url in all_responses[-20:]:  # Last 20
                print(f"   [{status}] {ct[:40]:40s} {url[:80]}")

            # Check if there's a sciencedirect CDN URL
            cdn_urls = [url for _, _, url in all_responses if "sciencedirect" in url or "pdf" in url.lower()]
            if cdn_urls:
                print(f"\n   → Found {len(cdn_urls)} CDN/PDF URLs, trying to fetch...")
                for cdn_url in cdn_urls[:3]:
                    print(f"   → GET {cdn_url[:80]}")
                    try:
                        r = pdf_page.goto(cdn_url, wait_until="commit", timeout=10_000)
                        time.sleep(2)
                    except:
                        pass

        # ── Step 6: Result ────────────────────────────────────────────────────
        if pdf_captured:
            data = pdf_captured[0]
            with open(OUT_PDF, "wb") as f:
                f.write(data)
            print(f"\n✅ SUCCESS — PDF saved ({len(data):,} bytes) → {OUT_PDF}")
            print("→ ARCHITECTURE CONFIRMED: Real Chrome in Electron will work.")
        else:
            print(f"\n❌ PDF not captured via response interception.")
            print("→ AJOG likely serves PDF in an iframe or embedded viewer.")
            print("→ Next approach: intercept requests at CDP level or use page.pdf()")

        input("\nPress Enter to close Chrome...")
        browser.close()
        proc.terminate()

    print("=" * 60)

if __name__ == "__main__":
    run()
