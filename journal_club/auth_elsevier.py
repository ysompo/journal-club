# journal_club/auth_elsevier.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def authenticate_elsevier(page: Page, article_url: str, email: str, password: str,
                           captured: list):
    """Elsevier/ScienceDirect auth flow."""
    print(f"\n[Elsevier Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)

    # If the Chrome extension already captured the PDF (cached session), skip auth entirely
    if captured:
        print("   [Elsevier] PDF captured during navigation — skipping auth")
        return

    dismiss_cookies(page)
    for sel in [
        "text=Get access",
        "button:has-text('Get access')",
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('Institutional access')",
        "#access-options",
        "button.buybox__btn",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue
    for sel in [
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('institution')",
        "a[href*='openathens']",
        "a[href*='shibboleth']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked institution link: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue
    print(f"   On: {page.url[:80]}")
    try:
        page.wait_for_function(
            """() => window.location.href.includes('wayfinder') ||
                     window.location.href.includes('openathens') ||
                     window.location.href.includes('huji.ac.il')""",
            timeout=30_000,
        )
        current = page.url
        if "wayfinder" in current or "openathens" in current:
            dismiss_cookies(page)
            time.sleep(1)
            for sel in ['input[placeholder*="nstitut"]', 'input[type="search"]', 'input[type="text"]']:
                try:
                    page.click(sel, timeout=3000)
                    page.type(sel, "Hebrew University of Jerusalem", delay=50)
                    time.sleep(2)
                    break
                except Exception:
                    continue
            for sel in [
                "span:has-text('Hebrew University of Jerusalem')",
                "li:has-text('Hebrew University')",
                "a:has-text('Hebrew University')",
                "[role='option']:has-text('Hebrew')",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    time.sleep(2)
                    break
                except Exception:
                    continue
    except Exception as e:
        print(f"   [Elsevier] Timeout: {e}")
    wait_for_huji_and_login(page, email, password)
    print("\n[Elsevier] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => !window.location.href.includes('huji.ac.il') &&
                     !window.location.href.includes('openathens') &&
                     !window.location.href.includes('login')""",
            timeout=90_000,
        )
        print(f"   Back: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")
    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)

    print("\n[Elsevier] Extracting PDF URL from authenticated page...")
    try:
        pdf_url = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const pdf = links.find(a =>
                (a.href.includes('pdfft') || a.href.includes('/pdf/') ||
                 a.href.endsWith('.pdf') || a.href.includes('pdf.sciencedirect')) &&
                (a.innerText || a.textContent || '').toLowerCase().includes('pdf')
            );
            return pdf ? pdf.href : null;
        }""")
    except Exception as e:
        print(f"   [Elsevier] PDF URL eval error (page may have navigated): {e}")
        pdf_url = None

    if pdf_url:
        print(f"   PDF URL: {pdf_url[:80]}")
        pdf_tab = page.context.new_page()
        pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
        from journal_club.pdf_capture import wait_for_pdf
        if not wait_for_pdf(captured, timeout_s=45):
            print("   [Elsevier] Retrying PDF navigation...")
            pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
            wait_for_pdf(captured, timeout_s=30)
    else:
        print("   No PDF URL in DOM — clicking Download PDF button...")
        for sel in [
            "a:has-text('Download PDF')",
            "button:has-text('Download PDF')",
            "a[href*='pdfft']",
            "a[href$='.pdf']",
        ]:
            try:
                page.click(sel, timeout=5000)
                print(f"   [Elsevier] Clicked: {sel}")
                break
            except Exception:
                continue
