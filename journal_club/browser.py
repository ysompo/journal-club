# journal_club/browser.py
import os
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


@contextmanager
def launch_browser(profile_dir: str, chrome_path: str = "", port: int = 9222,
                   start_url: str = "about:blank"):
    """
    Context manager: launches Chrome with remote debugging, yields (playwright, browser, context, page).
    Cleans up on exit.
    """
    os.makedirs(profile_dir, exist_ok=True)
    chrome = find_chrome(chrome_path)

    proc = subprocess.Popen([
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
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
