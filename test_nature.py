"""
Nature Auth Test
Strategy:
  1. Navigate to article page
  2. Try downloading PDF directly (open-access check)
  3. Only if blocked, go through institutional auth (SpringerNature -> OpenAthens -> HUJI)
"""

import subprocess
import time
import os
import sys
from playwright.sync_api import sync_playwright

ARTICLE_URL = "https://www.nature.com/articles/s41591-026-04256-2"
OUT_PDF     = "test_nature.pdf"

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
    print("Nature Auth Test")
    print("=" * 60)

    chrome_path = find_chrome()
    if not chrome_path:
        print("Chrome not found.")
        sys.exit(1)

    creds_file = r"C:\Users\ysomp\OneDrive\Desktop\test.txt"
    with open(creds_file) as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    huji_email    = lines[0]
    huji_password = lines[1]
    print(f"   Credentials loaded\n")

    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-nature-test2")
    os.makedirs(tmp_profile, exist_ok=True)

    print("[Step 1] Launching Chrome...")
    proc = subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={tmp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        ARTICLE_URL
    ])
    time.sleep(4)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        pages   = context.pages
        page    = pages[0] if pages else context.new_page()

        pdf_captured = []

        def on_response(response):
            url = response.url
            ct  = response.headers.get("content-type", "")
            status = response.status
            if any(ext in url for ext in ['.ttf', '.woff', '.otf', '.eot', '.svg', '.css', '.js', '.png', '.jpg', '.gif', '.ico']):
                return
            if "pdf" in ct.lower() or "octet-stream" in ct.lower() or url.endswith('.pdf'):
                print(f"\n   [PDF] {status} | {ct[:40]} | {url[:80]}")
                if status == 200 and not pdf_captured:
                    try:
                        body = response.body()
                        if body[:4] == b'%PDF':
                            print(f"   Valid PDF — {len(body):,} bytes")
                            pdf_captured.append(body)
                            with open(OUT_PDF, "wb") as f:
                                f.write(body)
                            print(f"   Saved -> {OUT_PDF}")
                        else:
                            print(f"   Not PDF header: {body[:8]}")
                    except Exception as e:
                        print(f"   Body error: {e}")

        def on_download(download):
            print(f"\n   [DOWNLOAD] {download.suggested_filename}")
            path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), download.suggested_filename)
            download.save_as(path)
            with open(path, "rb") as f:
                body = f.read()
            if body[:4] == b'%PDF':
                print(f"   Valid PDF via download — {len(body):,} bytes")
                with open(OUT_PDF, "wb") as f:
                    f.write(body)
                print(f"   Saved -> {OUT_PDF}")
                pdf_captured.append(body)

        def on_new_page(new_page):
            print(f"   -> New tab: {new_page.url}")
            new_page.on("response", on_response)
            new_page.on("download", on_download)

        context.on("page", on_new_page)
        page.on("response", on_response)
        page.on("download", on_download)

        # Dismiss cookie banner
        time.sleep(3)
        for cookie_sel in ["button:has-text('Accept all cookies')", "button:has-text('Accept cookies')",
                           "button:has-text('I accept')", "button:has-text('Accept')"]:
            try:
                page.click(cookie_sel, timeout=3000)
                print(f"   Cookie banner dismissed")
                time.sleep(1)
                break
            except:
                continue

        print(f"\n[Step 2] Article page loaded: {page.url}")

        # ── Step 2: Try direct PDF download first (open access check) ─────────
        print("\n[Step 2] Checking for direct PDF access (open access)...")

        # Look for the PDF link in the DOM
        pdf_href = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const pdf = links.find(a =>
                a.href.endsWith('.pdf') &&
                a.href.includes('nature.com') &&
                (a.innerText||a.textContent||'').toLowerCase().includes('pdf')
            );
            return pdf ? pdf.href : null;
        }""")

        if pdf_href:
            print(f"   PDF link found: {pdf_href}")
            print(f"   Attempting direct download...")
            try:
                pdf_page = context.new_page()
                pdf_page.on("response", on_response)
                pdf_page.on("download", on_download)
                pdf_page.goto(pdf_href, wait_until="commit", timeout=20_000)
                time.sleep(8)
                print(f"   -> Landed on: {pdf_page.url[:80]}")
            except Exception as e:
                print(f"   Error: {e}")
        else:
            print("   No direct PDF link found in DOM")

        if pdf_captured:
            print("\n[Result] Open access — PDF saved without auth!")
        else:
            print("\n   Direct PDF not accessible — trying institutional auth...")

            # ── Step 3: Click Log in / Access through institution ──────────────
            print("\n[Step 3] Navigating to institutional login...")
            page.goto(ARTICLE_URL, wait_until="domcontentloaded")
            time.sleep(2)

            for sel in [
                "a:has-text('Access through your institution')",
                "a:has-text('Log in via your institution')",
                "button:has-text('Access through your institution')",
                "a:has-text('Log in')",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    print(f"   Clicked: {sel}")
                    time.sleep(3)
                    break
                except:
                    continue

            print(f"   -> On: {page.url[:80]}")

            # ── Step 4: Handle SpringerNature gateway ─────────────────────────
            print("\n[Step 4] Looking for institution option on gateway...")
            time.sleep(2)

            # Dump what's on the gateway page
            body_text = page.evaluate("() => document.body.innerText")
            print(f"   Gateway page (first 300): {body_text[:300]}")

            links = page.evaluate("""() => {
                const r = [];
                document.querySelectorAll('a, button').forEach(el => {
                    const t = (el.innerText||el.textContent||'').trim();
                    if (t && t.length < 80) r.push({tag:el.tagName, text:t, href:el.href||''});
                });
                return r.slice(0, 20);
            }""")
            print(f"   Links: {links}")

            # Click "Access through institution" on gateway
            for sel in [
                "a:has-text('Access through your institution')",
                "button:has-text('Access through your institution')",
                "a:has-text('institution')",
                "a:has-text('Shibboleth')",
                "a:has-text('OpenAthens')",
                "[data-test='institution-login']",
                "a:has-text('institutional access')",
            ]:
                try:
                    page.click(sel, timeout=3000)
                    print(f"   Clicked: {sel}")
                    time.sleep(3)
                    break
                except:
                    continue

            print(f"   -> On: {page.url[:80]}")

            # ── Step 5: OpenAthens institution search ─────────────────────────
            print("\n[Step 5] Institution search...")
            time.sleep(2)

            # Dismiss cookies on OpenAthens if needed
            for cookie_sel in ["button:has-text('Accept all cookies')", "button:has-text('Accept')", "button:has-text('OK')"]:
                try:
                    page.click(cookie_sel, timeout=3000)
                    print(f"   Cookie dismissed")
                    time.sleep(1)
                    break
                except:
                    continue

            # Type in institution search
            for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                        'input[placeholder*="rganiz"]', 'input[name="org"]',
                        'input[type="search"]', 'input.js-sa-institution-search', 'input[type="text"]']:
                try:
                    page.click(sel, timeout=3000)
                    page.type(sel, "Hebrew University of Jerusalem", delay=50)
                    print(f"   Typed institution: {sel}")
                    time.sleep(2)
                    break
                except:
                    continue

            # Click result
            for sel in ["li:has-text('Hebrew University')", "[role='option']:has-text('Hebrew')",
                        "a:has-text('Hebrew University')", "button:has-text('Hebrew University')",
                        "a.sa-institutionslink"]:
                try:
                    page.click(sel, timeout=5000)
                    print(f"   Selected institution: {sel}")
                    time.sleep(2)
                    break
                except:
                    continue

            print(f"   -> On: {page.url[:80]}")

            # ── Step 6: HUJI login ────────────────────────────────────────────
            print("\n[Step 6] Waiting for HUJI login page...")
            try:
                page.wait_for_function(
                    "() => window.location.href.includes('huji.ac.il')",
                    timeout=30_000
                )
                print(f"   On HUJI: {page.url[:60]}")
                time.sleep(1)

                for sel in ["text=With E-mail password", "a:has-text('E-mail password')", "[role='tab']:has-text('E-mail')"]:
                    try:
                        page.click(sel, timeout=4000)
                        print(f"   Clicked email tab")
                        time.sleep(1)
                        break
                    except:
                        continue

                for sel in ['input[type="email"]', 'input[name="username"]', '#username', 'input[placeholder*="mail"]']:
                    try:
                        val = page.input_value(sel)
                        if not val:
                            page.fill(sel, huji_email, timeout=3000)
                        print(f"   Email filled")
                        break
                    except:
                        continue

                for sel in ['input[type="password"]', 'input[name="password"]', '#password']:
                    try:
                        page.fill(sel, huji_password, timeout=3000)
                        print(f"   Password filled")
                        break
                    except:
                        continue

                for sel in ['button:has-text("Enter")', 'button[type="submit"]', 'input[type="submit"]']:
                    try:
                        page.click(sel, timeout=3000)
                        print(f"   Submitted")
                        break
                    except:
                        continue

            except Exception as e:
                print(f"   HUJI timeout: {e} — complete manually")
                time.sleep(20)

            # ── Step 7: Wait to return to Nature ─────────────────────────────
            print("\n[Step 7] Waiting to return to Nature...")
            try:
                page.wait_for_function(
                    """() => window.location.href.includes('nature.com') &&
                             !window.location.href.includes('login') &&
                             !window.location.href.includes('idp')""",
                    timeout=90_000
                )
                print(f"   Back on Nature: {page.url}")
            except:
                print(f"   Timeout. URL: {page.url}")

            time.sleep(3)
            page.goto(ARTICLE_URL, wait_until="domcontentloaded")
            time.sleep(3)
            print(f"   -> Article: {page.url}")

            # ── Step 8: Click Download PDF ────────────────────────────────────
            print("\n[Step 8] Clicking Download PDF...")
            for sel in ["a:has-text('Download PDF')", "button:has-text('Download PDF')",
                        "a[href$='.pdf']", "a:has-text('PDF')"]:
                try:
                    page.click(sel, timeout=5000)
                    print(f"   Clicked: {sel}")
                    break
                except:
                    continue

            print("   Intercepting for 30 seconds...")
            for i in range(30, 0, -5):
                if pdf_captured:
                    break
                print(f"   ... {i}s remaining")
                time.sleep(5)

        # ── Result ────────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        if os.path.exists(OUT_PDF) and os.path.getsize(OUT_PDF) > 10000:
            print(f"SUCCESS — {OUT_PDF} ({os.path.getsize(OUT_PDF):,} bytes)")
        else:
            print("PDF not saved — review output above")
            print(f"Current URL: {page.url}")
        print("=" * 60)

        try:
            input("\nPress Enter to close Chrome...")
        except EOFError:
            pass
        browser.close()
        proc.terminate()

if __name__ == "__main__":
    run()
