# journal_club/browser.py
import os
import json
import subprocess
import time
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

def find_chrome(override: str = "") -> str:
    if override and os.path.exists(override):
        return override
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Google Chrome not found. Install Chrome or set chrome_path in config.yaml")


def _ensure_pdf_download_preference(profile_dir: str) -> None:
    """
    Set Chrome's 'always_open_pdf_externally' preference so PDFs are downloaded
    rather than opened in Chrome's built-in PDF viewer.  This allows Playwright's
    on_download hook to capture the PDF bytes instead of having Chrome consume
    the response before CDP can read it back.
    Must be called BEFORE Chrome launches (i.e. before launch_browser).
    """
    prefs_path = os.path.join(profile_dir, "Default", "Preferences")
    try:
        os.makedirs(os.path.dirname(prefs_path), exist_ok=True)
        # Grant full control to current user via icacls (handles Windows ACL denials).
        # Run on the Default/ directory (with /T for inheritance) so the grant applies
        # even when the Preferences file doesn't yet exist.
        username = os.environ.get("USERNAME", "Users")
        default_dir = os.path.dirname(prefs_path)
        subprocess.run(
            ["icacls", default_dir, "/grant", f"{username}:(F)", "/T", "/Q"],
            capture_output=True, timeout=10,
        )
        # Also unlock read-only flag (handles crashed-session lock)
        if os.path.exists(prefs_path):
            import stat
            os.chmod(prefs_path, stat.S_IREAD | stat.S_IWRITE)
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
        else:
            prefs = {}
        prefs.setdefault("plugins", {})["always_open_pdf_externally"] = True
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        print("   [Browser] PDF download preference set.")
    except Exception as e:
        print(f"   [Browser] Could not set PDF download preference: {e}")


def set_download_behavior(context: BrowserContext, page: Page,
                          download_dir: str) -> None:
    """
    Tell Chrome (via CDP) to save all downloads to *download_dir* and emit
    download-progress events.  This is a belt-and-suspenders complement to
    the 'always_open_pdf_externally' preference: it ensures the on_download
    Playwright hook fires even for responses that Chrome would otherwise open
    inline (e.g., application/pdf or application/octet-stream).
    Call this AFTER attach_pdf_hooks() and BEFORE any navigation.
    """
    try:
        abs_dir = os.path.abspath(download_dir)
        os.makedirs(abs_dir, exist_ok=True)
        cdp = context.new_cdp_session(page)
        cdp.send("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": abs_dir,
            "eventsEnabled": True,
        })
        print(f"   [Browser] CDP download behavior → {abs_dir}")
    except Exception as e:
        print(f"   [Browser] setDownloadBehavior error: {e}")


@contextmanager
def launch_browser(profile_dir: str, chrome_path: str = "", port: int = 9222,
                   start_url: str = "about:blank"):
    """
    Context manager: launches Chrome with remote debugging, yields (playwright, browser, context, page).
    Cleans up on exit.
    """
    os.makedirs(profile_dir, exist_ok=True)
    _ensure_pdf_download_preference(profile_dir)
    chrome = find_chrome(chrome_path)

    proc = subprocess.Popen([
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        # Disable Chrome's built-in PDF viewer so PDFs are downloaded as files
        # rather than rendered inline.  Inline rendering consumes the response
        # bytes before CDP can read them back, causing response.body() to fail.
        "--disable-pdf-extension",
        start_url,
    ])
    time.sleep(4)   # wait for Chrome DevTools protocol to become available

    with sync_playwright() as p:
        browser: Browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
        context: BrowserContext = browser.contexts[0] if browser.contexts else browser.new_context()
        pages = context.pages
        page: Page = pages[0] if pages else context.new_page()
        try:
            yield p, browser, context, page
        finally:
            try:
                browser.close()
            except Exception:
                pass
            proc.terminate()
