"""
AJOG Auth Test — Phase 7 (Fully Automated)
- Collects HUJI credentials once via secure terminal prompt
- Drives the full auth flow automatically: Get Access → OpenAthens → HUJI login
- Extracts real PDF URL from authenticated DOM
- Intercepts PDF response bytes and saves to disk
"""

import subprocess
import time
import os
import sys
import getpass
from playwright.sync_api import sync_playwright

ARTICLE_URL = "https://www.ajog.org/article/S0002-9378(26)00179-1/fulltext"
OUT_PDF     = "test_download.pdf"

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

def wait_for_url(page, containing, timeout=60_000):
    page.wait_for_function(
        f"() => window.location.href.includes('{containing}')",
        timeout=timeout
    )

def run():
    print("=" * 60)
    print("AJOG Auth Test — Fully Automated")
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
    print(f"   ✅ Credentials loaded from file\n")

    tmp_profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chrome-journal-test11")
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

        # Dismiss cookie banner
        try:
            page.click("button:has-text('Accept all cookies')", timeout=4000)
            print("   → Cookie banner dismissed")
        except:
            pass

        time.sleep(2)

        # ── Step 2: Click Get Access ──────────────────────────────────────────
        print("\n[Step 2] Clicking 'Get access'...")
        try:
            page.click("text=Get access", timeout=6000)
            print("   ✅ Clicked 'Get access'")
            time.sleep(2)
        except:
            print("   ⚠ 'Get access' not found — may already be authenticated or page not loaded")

        # ── Step 3: Click 'Access through your institution' ───────────────────
        print("\n[Step 3] Clicking 'Access through your institution'...")
        try:
            page.click("text=Access through your institution", timeout=6000)
            print("   ✅ Clicked")
            time.sleep(2)
        except:
            print("   ⚠ Not found — trying alternate selectors...")
            try:
                page.click("[data-aa-button='institution']", timeout=3000)
            except:
                print("   ⚠ Please click 'Access through your institution' manually")
                time.sleep(5)

        # ── Step 4: Institution selector on id.elsevier.com ─────────────────
        print("\n[Step 4] Waiting for Elsevier 'Find your organization' page...")
        try:
            # Wait for id.elsevier.com or openathens
            page.wait_for_function(
                """() => window.location.href.includes('id.elsevier.com') ||
                         window.location.href.includes('openathens') ||
                         document.querySelector('input[placeholder*="rganization"], input[placeholder*="nstitution"], input[name="org"]') !== null""",
                timeout=20_000
            )
            print(f"   ✅ On institution selector: {page.url[:60]}")
            time.sleep(1)

            # Dismiss Elsevier cookie banner (id.elsevier.com has its own banner)
            print("   → Dismissing cookie banner...")
            for cookie_sel in [
                "button:has-text('Accept all cookies')",
                "button:has-text('Accept only necessary cookies')",
                "button:has-text('Accept all')",
                "button:has-text('I agree')",
            ]:
                try:
                    page.click(cookie_sel, timeout=3000)
                    print(f"   ✅ Cookie banner dismissed: {cookie_sel}")
                    time.sleep(1)
                    break
                except:
                    continue

            # Now fill in the institution name
            org_input = None
            for sel in [
                'input[placeholder*="rganization"]',
                'input[placeholder*="nstitution"]',
                'input[placeholder*="email"]',
                'input[name="org"]',
                'input[type="text"]',
                'input[type="search"]',
            ]:
                try:
                    page.fill(sel, "Hebrew University of Jerusalem", timeout=3000)
                    org_input = sel
                    print(f"   ✅ Typed institution into: {sel}")
                    break
                except:
                    continue

            if not org_input:
                print("   ⚠ Input not found — please type 'Hebrew University of Jerusalem' manually")
                time.sleep(10)
            else:
                time.sleep(2)
                # Click the dropdown suggestion
                for sel in [
                    "text=Hebrew University of Jerusalem",
                    "li:has-text('Hebrew University')",
                    "[role='option']:has-text('Hebrew')",
                    ".result:has-text('Hebrew')",
                    "button:has-text('Submit')",
                    "button:has-text('Continue')",
                ]:
                    try:
                        page.click(sel, timeout=4000)
                        print(f"   ✅ Selected institution: {sel}")
                        break
                    except:
                        continue
                else:
                    print("   ⚠ Please click 'Hebrew University of Jerusalem' in the list manually")
                    time.sleep(10)

        except Exception as e:
            print(f"   ⚠ Institution selector error: {e}")
            print("   Please complete institution selection manually")
            time.sleep(12)

        # ── Step 5: HUJI login ────────────────────────────────────────────────
        print("\n[Step 5] Waiting for HUJI login page...")
        try:
            page.wait_for_function(
                "() => window.location.href.includes('huji.ac.il')",
                timeout=30_000
            )
            print(f"   ✅ On HUJI IdP: {page.url[:60]}")
            time.sleep(1)

            # CRITICAL: HUJI defaults to "With temporary code" tab.
            # Must click "With E-mail password" tab first.
            print("   → Clicking 'With E-mail password' tab...")
            for sel in [
                "text=With E-mail password",
                "button:has-text('E-mail password')",
                "a:has-text('E-mail password')",
                "[role='tab']:has-text('E-mail')",
            ]:
                try:
                    page.click(sel, timeout=4000)
                    print(f"   ✅ Clicked email/password tab: {sel}")
                    time.sleep(1)
                    break
                except:
                    continue
            else:
                print("   ⚠ Could not find email tab — please click 'With E-mail password' manually")
                time.sleep(5)

            # Fill email (may already be pre-filled)
            for sel in ['input[type="email"]', 'input[name="username"]', '#username',
                        'input[placeholder*="mail"]', 'input[placeholder*="E-mail"]']:
                try:
                    current = page.input_value(sel)
                    if current:
                        print(f"   → Email already filled: {current}")
                    else:
                        page.fill(sel, huji_email, timeout=3000)
                        print(f"   ✅ Email filled: {sel}")
                    break
                except:
                    continue

            # Fill password
            for sel in ['input[type="password"]', 'input[name="password"]', '#password']:
                try:
                    page.fill(sel, huji_password, timeout=3000)
                    print(f"   ✅ Password filled: {sel}")
                    break
                except:
                    continue

            # Submit
            for sel in ['button:has-text("Enter")', 'button[type="submit"]', 'input[type="submit"]',
                        'button:has-text("Log in")', 'button:has-text("Sign in")']:
                try:
                    page.click(sel, timeout=3000)
                    print(f"   ✅ Submitted: {sel}")
                    break
                except:
                    continue

        except Exception as e:
            print(f"   ⚠ HUJI login error: {e}")
            print("   Please complete login manually")
            time.sleep(15)

        # ── Step 6: Wait to land back on AJOG ────────────────────────────────
        print("\n[Step 6] Waiting to return to AJOG after auth...")
        try:
            page.wait_for_function(
                """() => {
                    const url = window.location.href;
                    return url.includes('ajog.org') &&
                           !url.includes('idp') &&
                           !url.includes('openathens') &&
                           !url.includes('login');
                }""",
                timeout=60_000
            )
            print(f"   ✅ Back on AJOG: {page.url}")
        except:
            print(f"   ⚠ Timeout. Current URL: {page.url}")

        time.sleep(2)

        # Navigate explicitly back to fulltext (auth redirect may have gone to abstract)
        print(f"\n[Step 6b] Navigating back to fulltext page to ensure PDF access...")
        page.goto(ARTICLE_URL, wait_until="domcontentloaded")
        time.sleep(3)
        print(f"   → Now on: {page.url}")

        # ── Step 7: Extract real PDF URL from authenticated DOM ───────────────
        print("\n[Step 7] Extracting PDF links from authenticated page DOM...")
        pdf_links = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href || '';
                    const text = (a.innerText || a.textContent || '').trim();
                    if (href.toLowerCase().includes('pdf') ||
                        text.toLowerCase().includes('pdf') ||
                        text.toLowerCase().includes('download')) {
                        results.push({ href, text });
                    }
                });
                document.querySelectorAll('[class*="pdf"],[class*="download"]').forEach(el => {
                    results.push({
                        href: el.href || el.getAttribute('data-href') || '',
                        text: (el.innerText || el.textContent || '').trim(),
                        tag: el.tagName,
                    });
                });
                return results;
            }
        """)
        print(f"   Found {len(pdf_links)} PDF-related elements:")
        for link in pdf_links:
            print(f"   [{link.get('tag','A')}] \"{link.get('text','')}\" → {link.get('href','')[:80]}")

        # ── Step 8: Intercept PDF response and click download ─────────────────
        print("\n[Step 8] Setting up response interception and clicking Download PDF...")
        pdf_captured = []

        def on_response(response):
            ct     = response.headers.get("content-type", "")
            url    = response.url
            status = response.status
            if "pdf" in ct.lower() or "octet-stream" in ct.lower():
                print(f"\n   [PDF RESPONSE] {status} | {ct} | {url[:80]}")
                if status == 200 and not pdf_captured:
                    try:
                        body = response.body()
                        if body[:4] == b'%PDF':
                            print(f"   ✅ Valid PDF — {len(body):,} bytes")
                            pdf_captured.append(body)
                            # Save immediately on capture
                            with open(OUT_PDF, "wb") as f:
                                f.write(body)
                            print(f"   ✅ Saved to {OUT_PDF}")
                    except Exception as e:
                        print(f"   Body error: {e}")

        page.on("response", on_response)

        for sel in ["a[href*='pdf']:visible", "text=Download PDF", "[aria-label*='PDF']"]:
            try:
                page.click(sel, timeout=4000)
                print(f"   ✅ Clicked: {sel}")
                break
            except:
                continue

        time.sleep(10)  # Wait long enough for 4MB PDF response event to fire

        # ── Step 9: Browser fetch fallback ────────────────────────────────────
        if not pdf_captured:
            real_url = next((l['href'] for l in pdf_links if 'pdf' in l.get('href','').lower()), None)
            if real_url:
                print(f"\n[Step 9] Browser fetch on: {real_url[:80]}")
                result = page.evaluate(f"""
                    async () => {{
                        const r = await fetch("{real_url}", {{credentials:'include', redirect:'follow'}});
                        const buf = await r.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        return {{
                            status: r.status,
                            finalUrl: r.url,
                            ct: r.headers.get('content-type') || '',
                            size: bytes.length,
                            header: String.fromCharCode(...bytes.slice(0,4))
                        }};
                    }}
                """)
                print(f"   Status: {result['status']} | CT: {result['ct']}")
                print(f"   Final URL: {result['finalUrl'][:80]}")
                print(f"   Size: {result['size']:,} | Header: '{result['header']}'")
                if result['header'] == '%PDF':
                    print(f"   ✅ PDF confirmed via browser fetch!")

        # ── Result ────────────────────────────────────────────────────────────
        if pdf_captured:
            with open(OUT_PDF, "wb") as f:
                f.write(pdf_captured[0])
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS — PDF saved ({len(pdf_captured[0]):,} bytes) → {OUT_PDF}")
            print("→ ARCHITECTURE CONFIRMED: Electron BrowserWindow will work.")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print("❌ PDF not captured automatically — check output above for clues")
            print(f"{'='*60}")

        input("\nPress Enter to close Chrome...")
        browser.close()
        proc.terminate()

if __name__ == "__main__":
    run()
