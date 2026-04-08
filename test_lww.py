"""
LWW (Wolters Kluwer) Auth Test — journals.lww.com
Strategy:
  1. Navigate to article page
  2. Try direct PDF access (open access check)
  3. If blocked, go through institutional auth (OpenAthens -> HUJI)
"""

import subprocess
import time
import os
import sys
from playwright.sync_api import sync_playwright

ARTICLE_URL     = "https://journals.lww.com/greenjournal/citation/2026/04001/artificial_intelligence_based_risk_calculator_for.4.aspx"
FULLTEXT_URL    = "https://journals.lww.com/greenjournal/fulltext/2026/04001/artificial_intelligence_based_risk_calculator_for.4.aspx"
OVID_LOGIN_URL  = "https://login.journals.lww.com/OneID/Login.aspx?returnUrl=https://journals.lww.com/greenjournal/fulltext/2026/04001/artificial_intelligence_based_risk_calculator_for.4.aspx&Login_type=Ovid"
OUT_PDF     = "test_lww.pdf"

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
    print("LWW Auth Test")
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

    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-lww-test1")
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
    time.sleep(5)

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
            print(f"   -> New tab: {new_page.url[:60]}")
            new_page.on("response", on_response)
            new_page.on("download", on_download)

        context.on("page", on_new_page)
        page.on("response", on_response)
        page.on("download", on_download)

        # Dismiss cookie banner
        time.sleep(4)
        for cookie_sel in ["button:has-text('Accept All Cookies')", "button:has-text('Accept all cookies')",
                           "button:has-text('Accept')", "button:has-text('I Accept')"]:
            try:
                page.click(cookie_sel, timeout=4000)
                print(f"   Cookie banner dismissed")
                time.sleep(1)
                break
            except:
                continue

        print(f"\n[Step 2] Article page: {page.url[:80]}")

        # Dump access buttons to understand page state
        buttons = page.evaluate("""() => {
            const r = [];
            document.querySelectorAll('a, button').forEach(el => {
                const t = (el.innerText||el.textContent||'').trim();
                if (t && t.length < 80 && /pdf|access|download|full.?text|get|log.?in|sign.?in|open/i.test(t))
                    r.push({tag: el.tagName, text: t, href: el.href||''});
            });
            return r.slice(0, 15);
        }""")
        print(f"   Access/PDF buttons: {buttons}")

        # ── Step 2: Navigate to fulltext and try PDF button directly ─────────
        print("\n[Step 2] Trying PDF button on fulltext page (open access check)...")
        page.goto(FULLTEXT_URL, wait_until="domcontentloaded")
        time.sleep(4)
        print(f"   -> On: {page.url[:80]}")

        # Try clicking Download -> PDF (dropdown pattern)
        try:
            page.click("button:has-text('Download')", timeout=4000)
            print(f"   Clicked Download dropdown")
            time.sleep(2)
            page.click("button:has-text('PDF')", timeout=4000)
            print(f"   Clicked PDF option")
            time.sleep(8)
        except Exception as e:
            print(f"   Download->PDF click failed: {e}")
            for sel in ["a:has-text('PDF')", "a[href*='.pdf']"]:
                try:
                    page.click(sel, timeout=4000)
                    print(f"   Fallback clicked: {sel}")
                    time.sleep(8)
                    break
                except:
                    continue

        if pdf_captured:
            print("\n[Result] Open access — PDF saved without auth!")
        else:
            print("\n   PDF not directly accessible — trying institutional auth...")

            # ── Step 3: Navigate directly to Ovid institutional login ─────────
            print("\n[Step 3] Navigating to Ovid institutional login...")
            page.goto(OVID_LOGIN_URL, wait_until="domcontentloaded")
            time.sleep(3)
            print(f"   -> On: {page.url[:80]}")

            # Dump Ovid login page
            body_text = page.evaluate("() => document.body.innerText")
            print(f"   Page (first 500): {body_text[:500]}")
            all_btns = page.evaluate("""() => {
                const r = [];
                document.querySelectorAll('a, button').forEach(el => {
                    const t = (el.innerText||el.textContent||'').trim();
                    if (t && t.length < 100)
                        r.push({tag: el.tagName, text: t.slice(0,60), href: (el.href||'').slice(0,80)});
                });
                return r.slice(0, 20);
            }""")
            print(f"   Buttons: {all_btns}")

            # ── Step 4: Find and click institutional/OpenAthens option ────────
            print("\n[Step 4] Finding OpenAthens/institutional option...")
            time.sleep(2)

            for sel in [
                "a:has-text('OpenAthens')",
                "a:has-text('Shibboleth')",
                "a:has-text('institution')",
                "button:has-text('OpenAthens')",
                "button:has-text('institution')",
                "[href*='openathens']",
                "[href*='shibboleth']",
            ]:
                try:
                    page.click(sel, timeout=4000)
                    print(f"   Clicked: {sel}")
                    time.sleep(3)
                    break
                except:
                    continue

            print(f"   -> On: {page.url[:80]}")

            # Dismiss cookies
            for cookie_sel in ["button:has-text('Accept all cookies')", "button:has-text('Accept')", "button:has-text('OK')"]:
                try:
                    page.click(cookie_sel, timeout=3000)
                    print(f"   Cookie dismissed")
                    time.sleep(1)
                    break
                except:
                    continue

            # ── Step 5: Institution search (wayfinder.openathens.net) ──────────
            print("\n[Step 5] Searching for institution...")
            time.sleep(2)

            # Dismiss cookies if any
            for cookie_sel in ["button:has-text('Accept all cookies')", "button:has-text('Accept')", "button:has-text('OK')"]:
                try:
                    page.click(cookie_sel, timeout=2000)
                    print(f"   Cookie dismissed")
                    time.sleep(1)
                    break
                except:
                    continue

            # Type institution name
            for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                        'input[placeholder*="rganiz"]', 'input[name="org"]',
                        'input[type="search"]', 'input.js-sa-institution-search', 'input[type="text"]']:
                try:
                    page.click(sel, timeout=3000)
                    page.type(sel, "Hebrew University of Jerusalem", delay=50)
                    print(f"   Typed institution: {sel}")
                    time.sleep(3)  # wait for dropdown
                    break
                except:
                    continue

            # Wait longer for dropdown to render, then dump ALL visible DOM
            time.sleep(5)
            full_body = page.evaluate("() => document.body.innerText")
            print(f"   Page after typing (first 600): {full_body[:600]}")

            # Find any element containing "Hebrew" text
            all_hebrew = page.evaluate("""() => {
                const r = [];
                document.querySelectorAll('*').forEach(el => {
                    const t = (el.innerText||'').trim();
                    if (t && /hebrew/i.test(t) && el.children.length === 0)
                        r.push({tag: el.tagName, cls: el.className.slice(0,40), text: t.slice(0,60)});
                });
                return r.slice(0, 10);
            }""")
            print(f"   Elements with 'Hebrew': {all_hebrew}")

            # Click the result — try broad approach first: click any element with Hebrew text
            clicked = False
            for sel in [
                "li:has-text('Hebrew University')",
                "[role='option']:has-text('Hebrew')",
                "[role='listitem']:has-text('Hebrew')",
                "button:has-text('Hebrew University')",
                "a:has-text('Hebrew University')",
                ".result:has-text('Hebrew')",
                ".suggestion:has-text('Hebrew')",
                ".institution:has-text('Hebrew')",
                "a.sa-institutionslink",
                "[data-institution*='Hebrew']",
                "li.ds-institution-result:has-text('Hebrew')",
                "span:has-text('Hebrew University of Jerusalem')",
                "p:has-text('Hebrew University of Jerusalem')",
            ]:
                try:
                    page.click(sel, timeout=3000)
                    print(f"   Selected HUJI: {sel}")
                    clicked = True
                    time.sleep(3)
                    break
                except:
                    continue

            if not clicked:
                # Try JS click on any element containing Hebrew
                try:
                    page.evaluate("""() => {
                        const all = document.querySelectorAll('*');
                        for (const el of all) {
                            if (/hebrew university/i.test(el.innerText||'') && el.children.length === 0) {
                                el.click(); return true;
                            }
                        }
                        return false;
                    }""")
                    print("   JS-clicked Hebrew element")
                    time.sleep(3)
                except Exception as e:
                    print(f"   JS click failed: {e}")

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

            # ── Step 7: Wait to return to LWW ─────────────────────────────────
            print("\n[Step 7] Waiting to return to LWW...")
            try:
                page.wait_for_function(
                    """() => window.location.href.includes('lww.com') &&
                             !window.location.href.includes('login') &&
                             !window.location.href.includes('idp')""",
                    timeout=90_000
                )
                print(f"   Back on LWW: {page.url[:80]}")
            except:
                print(f"   Timeout. URL: {page.url[:80]}")

            time.sleep(3)
            page.goto(FULLTEXT_URL, wait_until="domcontentloaded")
            time.sleep(3)
            print(f"   -> Article: {page.url[:80]}")

            # ── Step 8: Find and click PDF button ────────────────────────────────
            print("\n[Step 8] Finding PDF button...")
            time.sleep(2)
            pdf_links = page.evaluate("""() => {
                const r = [];
                document.querySelectorAll('a, button').forEach(el => {
                    const t = (el.innerText||el.textContent||'').trim();
                    const h = el.href || '';
                    if (/pdf|download/i.test(t) || /\.pdf|\/pdf\//i.test(h))
                        r.push({tag: el.tagName, text: t.slice(0,50), href: h.slice(0,80)});
                });
                return r.slice(0, 15);
            }""")
            print(f"   PDF-related elements: {pdf_links}")

            time.sleep(3)  # let page settle after navigation
            # Download is a dropdown — click it first, then PDF
            try:
                page.click("button:has-text('Download')", timeout=5000)
                print(f"   Clicked Download dropdown")
                time.sleep(2)
                page.click("button:has-text('PDF')", timeout=5000)
                print(f"   Clicked PDF option")
            except Exception as e:
                print(f"   Download->PDF failed: {e}")
                for sel in ["a:has-text('PDF')", "a[href*='.pdf']", "a:has-text('Download PDF')"]:
                    try:
                        page.click(sel, timeout=5000)
                        print(f"   Fallback clicked: {sel}")
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
            print(f"Current URL: {page.url[:80]}")
        print("=" * 60)

        try:
            input("\nPress Enter to close Chrome...")
        except EOFError:
            pass
        browser.close()
        proc.terminate()

if __name__ == "__main__":
    run()
