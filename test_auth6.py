"""
AJOG Auth Test — Phase 6
- Intercepts REQUESTS (not responses) to see redirect chain destinations
- Watches all frames (PDF may load in iframe viewer)
- Captures Location header from 302 to find the real CDN PDF URL
- Then fetches that URL directly
"""

import subprocess
import time
import os
import sys
from playwright.sync_api import sync_playwright

ARTICLE_URL  = "https://www.ajog.org/article/S0002-9378(26)00179-1/fulltext"
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
    print("AJOG Auth Test — Request Chain + Frame Interception")
    print("=" * 60)

    chrome_path = find_chrome()
    if not chrome_path:
        print("❌ Chrome not found.")
        sys.exit(1)

    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-journal-test4")
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
        print("   'Get access' → 'Access through your institution'")
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

        # ── Step 3: Track ALL requests across all frames ──────────────────────
        print("\n[Step 3] Intercepting all requests and responses across all frames...")

        all_requests  = []
        pdf_captured  = []
        cdn_pdf_url   = []

        def track_response(response):
            url  = response.url
            ct   = response.headers.get("content-type", "")
            loc  = response.headers.get("location", "")
            status = response.status

            # Log redirect destinations
            if status in (301, 302, 303, 307, 308) and loc:
                print(f"   [REDIRECT {status}] {url[:70]}")
                print(f"              → {loc[:70]}")
                all_requests.append(("redirect", url, loc))

            # Catch actual PDF bytes
            if "pdf" in ct.lower() or "application/octet-stream" in ct.lower():
                print(f"\n   [PDF RESPONSE] {url[:80]}")
                print(f"   Content-Type: {ct} | Status: {status}")
                if status == 200 and not pdf_captured:
                    try:
                        body = response.body()
                        if body[:4] == b'%PDF':
                            print(f"   ✅ Valid PDF — {len(body):,} bytes")
                            pdf_captured.append(body)
                        else:
                            print(f"   ⚠ Not PDF header: {body[:20]}")
                    except Exception as e:
                        print(f"   Body error: {e}")

            # Catch CDN asset URLs that look like PDFs
            if any(d in url for d in ["sciencedirectassets", "els-cdn", "elsevier"]):
                if "pdf" in url.lower() or "pdf" in ct.lower():
                    print(f"   [CDN PDF] {url[:80]}")
                    cdn_pdf_url.append(url)

        def track_request(request):
            url = request.url
            # Log any URL that looks like it could be the PDF
            if "pdf" in url.lower() or "sciencedirectassets" in url or "els-cdn" in url:
                print(f"   [REQUEST→PDF?] {url[:100]}")
                all_requests.append(("request", url, ""))

        # Attach to main page
        page.on("response", track_response)
        page.on("request",  track_request)

        # ── Step 4: Open showPdf ──────────────────────────────────────────────
        print(f"\n[Step 4] Navigating to showPdf URL (watching redirect chain)...")
        pdf_page = context.new_page()
        pdf_page.on("response", track_response)
        pdf_page.on("request",  track_request)

        try:
            pdf_page.goto(SHOW_PDF_URL, wait_until="networkidle", timeout=30_000)
            print(f"   → Final URL: {pdf_page.url}")
        except Exception as e:
            print(f"   → Note: {e}")
            print(f"   → Final URL: {pdf_page.url}")

        time.sleep(3)

        # ── Step 5: If we have a CDN URL, fetch its content via the browser ───
        if cdn_pdf_url and not pdf_captured:
            print(f"\n[Step 5] Fetching CDN PDF URL via browser JS fetch...")
            cdn = cdn_pdf_url[0]
            try:
                # Use browser's fetch() so it carries all cookies and passes Cloudflare
                result = pdf_page.evaluate(f"""
                    async () => {{
                        const r = await fetch("{cdn}", {{credentials: 'include'}});
                        const buf = await r.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        const header = String.fromCharCode(...bytes.slice(0,4));
                        return {{
                            status: r.status,
                            contentType: r.headers.get('content-type'),
                            size: bytes.length,
                            header: header
                        }};
                    }}
                """)
                print(f"   Status: {result['status']}")
                print(f"   Content-Type: {result['contentType']}")
                print(f"   Size: {result['size']:,} bytes")
                print(f"   Header: {result['header']}")
                if result['header'] == '%PDF':
                    print(f"   ✅ Valid PDF confirmed via browser fetch!")
            except Exception as e:
                print(f"   Error: {e}")

        # ── Step 6: Try page.evaluate fetch on the showPdf URL ────────────────
        if not pdf_captured and not cdn_pdf_url:
            print(f"\n[Step 5] Trying browser-native fetch on showPdf URL...")
            try:
                result = pdf_page.evaluate(f"""
                    async () => {{
                        const r = await fetch("{SHOW_PDF_URL}", {{
                            credentials: 'include',
                            redirect: 'follow'
                        }});
                        const buf = await r.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        return {{
                            status: r.status,
                            finalUrl: r.url,
                            contentType: r.headers.get('content-type'),
                            size: bytes.length,
                            header: String.fromCharCode(...bytes.slice(0,4))
                        }};
                    }}
                """)
                print(f"   Status: {result['status']}")
                print(f"   Final URL: {result['finalUrl']}")
                print(f"   Content-Type: {result['contentType']}")
                print(f"   Size: {result['size']:,} bytes")
                print(f"   Header bytes: {result['header']}")

                if result['header'] == '%PDF':
                    print(f"\n✅ PDF accessible via browser fetch!")
                    print(f"   Final URL: {result['finalUrl']}")
                    cdn_pdf_url.append(result['finalUrl'])
            except Exception as e:
                print(f"   Error: {e}")

        # ── Step 7: Save PDF if captured ──────────────────────────────────────
        if pdf_captured:
            with open(OUT_PDF, "wb") as f:
                f.write(pdf_captured[0])
            size = os.path.getsize(OUT_PDF)
            print(f"\n✅ SUCCESS — PDF saved ({size:,} bytes) → {OUT_PDF}")
        else:
            print(f"\n--- Summary of all redirect chains seen ---")
            for kind, url, dest in all_requests:
                if kind == "redirect":
                    print(f"  {url[:60]} → {dest[:60]}")

        input("\nPress Enter to close Chrome...")
        browser.close()
        proc.terminate()

    print("=" * 60)

if __name__ == "__main__":
    run()
