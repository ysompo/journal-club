# journal_club/auth_ovid.py
import os
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login

def _build_ovid_login_url(article_url: str) -> str:
    """Build the LWW/Ovid institutional login URL for the given article."""
    from urllib.parse import quote
    if "journals.lww.com" in article_url:
        # Convert citation URL to fulltext URL for the return target
        ft_url = article_url.replace("/citation/", "/fulltext/")
        encoded = quote(ft_url, safe="")
        return f"https://login.journals.lww.com/OneID/Login.aspx?returnUrl={encoded}&Login_type=Ovid"
    return "https://ovidsp.ovid.com/autologin.asp"

def _select_institution_on_wayfinder(page: Page):
    """On wayfinder.openathens.net: type HUJI and click the result span."""
    print("   [Ovid] On wayfinder — searching for HUJI...")
    for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                'input[name="institution"]', 'input[type="search"]', 'input[type="text"]']:
        try:
            page.click(sel, timeout=3000)
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [Ovid] Typed institution: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

    # The wayfinder result is a SPAN with class wayfinder-item-displayname-text
    for sel in [
        "span:has-text('Hebrew University of Jerusalem')",
        "button:has-text('Hebrew University')",
        "li:has-text('Hebrew University')",
        "[role='option']:has-text('Hebrew')",
        "a:has-text('Hebrew University')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Ovid] Selected institution: {sel}")
            time.sleep(2)
            return
        except Exception:
            continue
    print("   [Ovid] Could not click wayfinder result — check selectors")

def authenticate_ovid(page: Page, article_url: str, email: str, password: str,
                      captured: list, output_dir: str = None):
    """Full LWW/Ovid auth flow."""
    ovid_url = _build_ovid_login_url(article_url)
    print(f"\n[Ovid Auth] Navigating to Ovid login: {ovid_url[:60]}")
    page.goto(ovid_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    print(f"   On: {page.url[:80]}")

    # If page shows "previously used institution" card, click it directly
    for sel in [
        "button:has-text('Hebrew University of Jerusalem')",
        "a:has-text('Hebrew University of Jerusalem')",
        "[class*='institution']:has-text('Hebrew University')",
        "li:has-text('Hebrew University of Jerusalem')",
    ]:
        try:
            page.click(sel, timeout=3000)
            print(f"   [Ovid] Clicked previously-used institution: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue
    else:
        # Otherwise click "OpenAthens/Institutional login" to get to wayfinder
        for sel in [
            "a:has-text('OpenAthens')",
            "button:has-text('OpenAthens')",
            "a:has-text('Institutional')",
            "a:has-text('Institution')",
            "a:has-text('Find another institution')",
            "[data-target*='openathens']",
        ]:
            try:
                page.click(sel, timeout=5000)
                print(f"   [Ovid] Clicked: {sel}")
                time.sleep(3)
                break
            except Exception:
                continue

    print(f"   On: {page.url[:80]}")

    # Wait for wayfinder or HUJI
    try:
        page.wait_for_function(
            "() => window.location.href.includes('wayfinder') || window.location.href.includes('huji.ac.il')",
            timeout=20_000,
        )
        if "wayfinder" in page.url:
            _select_institution_on_wayfinder(page)
    except Exception as e:
        print(f"   [Ovid] Timeout waiting for wayfinder: {e}")

    wait_for_huji_and_login(page, email, password)

    # Wait to return to LWW
    print("\n[Ovid Auth] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => (window.location.href.includes('lww.com') ||
                      window.location.href.includes('ovid.com')) &&
                     !window.location.href.includes('login')""",
            timeout=90_000,
        )
        print(f"   Back on journal: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)
    # Navigate to fulltext URL (not citation URL — citation page has no download button)
    ft_url = article_url.replace("/citation/", "/fulltext/")
    page.goto(ft_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)

    # Try to find a direct PDF URL in the DOM first
    print("\n[Ovid Auth] Extracting PDF URL from authenticated page...")
    pdf_url = page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a[href]'));
        const pdf = links.find(a =>
            (a.href.includes('.pdf') || a.href.includes('pdf') || a.href.includes('PDF')) &&
            (a.innerText || a.textContent || '').toLowerCase().includes('pdf')
        );
        return pdf ? pdf.href : null;
    }""")

    if pdf_url:
        print(f"   PDF URL found: {pdf_url[:80]}")
        print("   Navigating directly to PDF URL...")
        pdf_tab = page.context.new_page()
        pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
        time.sleep(5)
    else:
        # Use expect_download() to synchronously wait for the download
        print("   No PDF URL in DOM — clicking Download PDF via expect_download...")
        try:
            # Open the Download dropdown first
            for download_sel in ["button:has-text('Download')", "a:has-text('Download')"]:
                try:
                    page.click(download_sel, timeout=5000)
                    print(f"   Clicked download toggle: {download_sel}")
                    time.sleep(1)
                    break
                except Exception:
                    continue

            # Now click PDF with expect_download to capture it synchronously
            with page.expect_download(timeout=60_000) as dl_info:
                for pdf_sel in ["button:has-text('PDF')", "a:has-text('PDF')", "li:has-text('PDF')"]:
                    try:
                        page.click(pdf_sel, timeout=5000)
                        print(f"   Clicked PDF: {pdf_sel}")
                        break
                    except Exception:
                        continue
            download = dl_info.value
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), download.suggested_filename)
            download.save_as(tmp)
            with open(tmp, "rb") as fh:
                body = fh.read()
            if body[:4] == b'%PDF':
                print(f"   [PDF via LWW download] {len(body):,} bytes")
                captured.append(body)
            else:
                print(f"   Download header not PDF: {body[:8]}")
        except Exception as e:
            print(f"   [Ovid] Download failed: {e}")
