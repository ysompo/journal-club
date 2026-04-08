"""
JAMA Auth Test
- Navigates directly to Shibboleth login (bypasses all popups)
- Uses confirmed selectors from live DOM inspection
"""

import subprocess
import time
import os
import sys
from playwright.sync_api import sync_playwright

ABSTRACT_URL = "https://jamanetwork.com/journals/jama/article-abstract/2844116"
SHIBBOLETH_URL = (
    "https://jamanetwork.com/signinshibboleth"
    "?returnUrl=https%3a%2f%2fjamanetwork.com%2fjournals%2fjama%2ffullarticle%2f2844116"
)
OUT_PDF = "test_jama.pdf"

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
    print("JAMA Auth Test")
    print("=" * 60)

    chrome_path = find_chrome()
    if not chrome_path:
        print("❌ Chrome not found.")
        sys.exit(1)

    creds_file = r"C:\Users\ysomp\OneDrive\Desktop\test.txt"
    with open(creds_file) as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    huji_email    = lines[0]
    huji_password = lines[1]
    print(f"   ✅ Credentials loaded\n")

    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-jama-test19")
    os.makedirs(tmp_profile, exist_ok=True)

    print("[Step 1] Launching Chrome...")
    proc = subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={tmp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank"
    ])
    time.sleep(4)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        pages   = context.pages
        page    = pages[0] if pages else context.new_page()

        # ── Step 2: Go directly to JAMA Shibboleth login (skips all popups) ──
        print("\n[Step 2] Navigating to institutional login page...")
        page.goto(SHIBBOLETH_URL, wait_until="domcontentloaded")
        time.sleep(2)
        print(f"   → On: {page.url}")

        # ── Step 3: Type institution and select from dropdown ─────────────────
        print("\n[Step 3] Selecting institution...")
        # Must use type() not fill() to trigger JS typeahead events
        page.click("input.js-sa-institution-search", timeout=10_000)
        page.type("input.js-sa-institution-search", "Hebrew University", delay=50)
        time.sleep(3)
        # Dropdown item confirmed: a.sa-institutionslink
        page.click("a.sa-institutionslink", timeout=10_000)
        print("   ✅ Selected: Hebrew University of Jerusalem")
        time.sleep(2)
        print(f"   → On: {page.url}")

        # ── Step 4: HUJI login ────────────────────────────────────────────────
        print("\n[Step 4] Waiting for HUJI login page (via OpenAthens)...")
        try:
            # First wait for either OpenAthens or HUJI
            page.wait_for_function(
                "() => window.location.href.includes('huji.ac.il') || window.location.href.includes('openathens')",
                timeout=30_000
            )
            print(f"   → Intermediate: {page.url[:80]}")

            # If on OpenAthens, dismiss cookie banner and wait for HUJI redirect
            if "openathens" in page.url:
                print("   → On OpenAthens, dismissing cookies and waiting for HUJI redirect...")
                for cookie_sel in ["button:has-text('Accept')", "button:has-text('I agree')",
                                   "button:has-text('Accept all')", "button:has-text('OK')"]:
                    try:
                        page.click(cookie_sel, timeout=3000)
                        print(f"   ✅ Cookie dismissed: {cookie_sel}")
                        time.sleep(1)
                        break
                    except:
                        continue
                # Dismiss cookie banner properly — click "Accept all cookies"
                for cookie_sel in ["button:has-text('Accept all cookies')",
                                   "button:has-text('Accept all')",
                                   "button:has-text('Accept necessary cookies')"]:
                    try:
                        page.click(cookie_sel, timeout=4000)
                        print(f"   ✅ OpenAthens cookies accepted: {cookie_sel}")
                        time.sleep(1)
                        break
                    except:
                        continue

                # Now search for HUJI in OpenAthens' institution search
                print("   → Searching for institution on OpenAthens...")
                for sel in ['input[placeholder*="nstitution"]', 'input[placeholder*="niversity"]',
                            'input[placeholder*="rganization"]', 'input[name="institution"]',
                            'input[type="search"]', 'input[type="text"]']:
                    try:
                        page.click(sel, timeout=3000)
                        page.type(sel, "Hebrew University of Jerusalem", delay=50)
                        print(f"   ✅ Typed institution into OpenAthens: {sel}")
                        time.sleep(2)
                        break
                    except:
                        continue

                # Click OpenAthens dropdown suggestion for HUJI
                for sel in ["li:has-text('Hebrew University')",
                            "[role='option']:has-text('Hebrew')",
                            "button:has-text('Hebrew University')",
                            "a:has-text('Hebrew University')",
                            ".result:has-text('Hebrew')"]:
                    try:
                        page.click(sel, timeout=5000)
                        print(f"   ✅ Selected HUJI from OpenAthens: {sel}")
                        time.sleep(2)
                        break
                    except:
                        continue

                print(f"   → After OpenAthens: {page.url[:80]}")

                # Now wait for HUJI
                page.wait_for_function(
                    "() => window.location.href.includes('huji.ac.il')",
                    timeout=30_000
                )

            print(f"   ✅ On HUJI: {page.url[:60]}")
            time.sleep(1)

            for sel in ["text=With E-mail password", "button:has-text('E-mail password')",
                        "a:has-text('E-mail password')", "[role='tab']:has-text('E-mail')"]:
                try:
                    page.click(sel, timeout=4000)
                    print(f"   ✅ Clicked email tab")
                    time.sleep(1)
                    break
                except:
                    continue

            for sel in ['input[type="email"]', 'input[name="username"]', '#username',
                        'input[placeholder*="mail"]']:
                try:
                    val = page.input_value(sel)
                    if val:
                        print(f"   → Email pre-filled: {val}")
                    else:
                        page.fill(sel, huji_email, timeout=3000)
                        print(f"   ✅ Email filled")
                    break
                except:
                    continue

            for sel in ['input[type="password"]', 'input[name="password"]', '#password']:
                try:
                    page.fill(sel, huji_password, timeout=3000)
                    print(f"   ✅ Password filled")
                    break
                except:
                    continue

            for sel in ['button:has-text("Enter")', 'button[type="submit"]',
                        'input[type="submit"]', 'button:has-text("Log in")']:
                try:
                    page.click(sel, timeout=3000)
                    print(f"   ✅ Submitted")
                    break
                except:
                    continue

        except Exception as e:
            print(f"   ⚠ HUJI login: {e} — please complete manually")
            time.sleep(20)

        # ── Step 5: Wait to return to JAMA ───────────────────────────────────
        print("\n[Step 5] Waiting to return to JAMA...")
        try:
            page.wait_for_function(
                """() => window.location.href.includes('jamanetwork.com') &&
                         !window.location.href.includes('login') &&
                         !window.location.href.includes('idp')""",
                timeout=90_000
            )
            print(f"   ✅ Back on JAMA: {page.url}")
        except:
            print(f"   ⚠ Timeout. URL: {page.url}")

        time.sleep(3)

        # ── Step 6: Navigate to full text + intercept PDF ────────────────────
        print("\n[Step 6] Navigating to full text...")
        ft_url = ABSTRACT_URL.replace("article-abstract", "fullarticle")
        print(f"   → {ft_url}")

        pdf_captured = []
        silverchair_urls = []  # Track Silverchair PDF URLs for fallback fetch

        def on_response(response):
            url = response.url
            ct  = response.headers.get("content-type", "")
            status = response.status
            # Skip noisy static assets
            if any(ext in url for ext in ['.ttf', '.woff', '.otf', '.eot', '.svg', '.css', '.js', '.png', '.jpg', '.gif', '.ico']):
                return
            if "pdf" in ct.lower() or "octet-stream" in ct.lower() or "pdf" in url.lower():
                print(f"\n   [PDF CANDIDATE] {status} | {ct} | {url[:80]}")
                # Track Silverchair URLs with full URL for later fetch
                if "silverchair" in url and status == 200:
                    silverchair_urls.append(url)
                if status == 200 and not pdf_captured:
                    try:
                        body = response.body()
                        if body[:4] == b'%PDF':
                            print(f"   ✅ Valid PDF — {len(body):,} bytes")
                            pdf_captured.append(body)
                            with open(OUT_PDF, "wb") as f:
                                f.write(body)
                            print(f"   ✅ Saved → {OUT_PDF}")
                        else:
                            print(f"   ⚠ Not PDF header: {body[:8]}")
                    except Exception as e:
                        print(f"   Body error: {e}")

        def on_download(download):
            print(f"\n   [DOWNLOAD] {download.suggested_filename}")
            path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), download.suggested_filename)
            download.save_as(path)
            with open(path, "rb") as f:
                body = f.read()
            if body[:4] == b'%PDF':
                print(f"   ✅ Valid PDF via download — {len(body):,} bytes")
                with open(OUT_PDF, "wb") as f:
                    f.write(body)
                print(f"   ✅ Saved → {OUT_PDF}")
                pdf_captured.append(body)

        def on_new_page(new_page):
            print(f"   → New tab: {new_page.url}")
            new_page.on("response", on_response)
            new_page.on("download", on_download)

        context.on("page", on_new_page)
        page.on("response", on_response)
        page.on("download", on_download)

        page.goto(ft_url, wait_until="domcontentloaded")
        time.sleep(3)
        print(f"   → Landed on: {page.url}")

        # ── Step 7: Auto-click Download PDF ──────────────────────────────────
        print("\n[Step 7] Auto-clicking Download PDF...")
        for sel in [
            "a:has-text('Download PDF')",
            "button:has-text('Download PDF')",
            "[aria-label*='Download PDF']",
            "a[href*='pdf']:has-text('Download')",
            "a[data-article-action='download-pdf']",
            ".article-tools__item--pdf a",
            "a.article-tools__item-pdf",
        ]:
            try:
                page.click(sel, timeout=5000)
                print(f"   ✅ Clicked PDF button: {sel}")
                break
            except:
                continue

        print("   Intercepting responses for 30 seconds...")
        for i in range(30, 0, -5):
            if pdf_captured:
                break
            print(f"   ... {i}s remaining")
            time.sleep(5)

        # Fallback: browser-side fetch of the Silverchair URL (has auth token in URL)
        if not pdf_captured and silverchair_urls:
            sc_url = silverchair_urls[0]
            print(f"\n   [Fallback] Browser fetch of Silverchair URL...")
            print(f"   → {sc_url[:80]}")
            try:
                # Find any open page to run the fetch from
                active_page = context.pages[-1] if context.pages else page
                result = active_page.evaluate(f"""
                    async () => {{
                        const r = await fetch({repr(sc_url)}, {{credentials: 'include', redirect: 'follow'}});
                        const buf = await r.arrayBuffer();
                        const bytes = Array.from(new Uint8Array(buf.slice(0, 4)));
                        const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
                        return {{status: r.status, ct: r.headers.get('content-type')||'', size: buf.byteLength, header: bytes, b64: b64}};
                    }}
                """)
                header_bytes = bytes(result['header'])
                print(f"   Status: {result['status']} | CT: {result['ct']} | Size: {result['size']:,} | Header: {header_bytes}")
                if header_bytes[:4] == b'%PDF':
                    import base64
                    body = base64.b64decode(result['b64'])
                    print(f"   ✅ Valid PDF via browser fetch — {len(body):,} bytes")
                    pdf_captured.append(body)
                    with open(OUT_PDF, "wb") as f:
                        f.write(body)
                    print(f"   ✅ Saved → {OUT_PDF}")
            except Exception as e:
                print(f"   Fetch error: {e}")

        # ── Result ────────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        if os.path.exists(OUT_PDF) and os.path.getsize(OUT_PDF) > 10000:
            print(f"✅ SUCCESS — {OUT_PDF} ({os.path.getsize(OUT_PDF):,} bytes)")
            print("→ JAMA confirmed working.")
        else:
            print("❌ PDF not saved — review output above")
        print("=" * 60)

        try:
            input("\nPress Enter to close Chrome...")
        except EOFError:
            pass
        browser.close()
        proc.terminate()

if __name__ == "__main__":
    run()
