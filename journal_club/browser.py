# journal_club/browser.py
import os
import json
import logging
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

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
    Context manager: launches Playwright's bundled Chromium with persistent context.
    Yields (playwright, browser, context, page). Cleans up on exit.
    Works on local machines, Render, Docker, and other containerized environments.

    Note: chrome_path parameter is ignored (uses bundled Chromium instead).
    """
    os.makedirs(profile_dir, exist_ok=True)
    logger.debug(f"[Browser] Profile dir: {profile_dir}")

    _ensure_pdf_download_preference(profile_dir)

    try:
        with sync_playwright() as p:
            logger.info("[Browser] Launching Playwright bundled Chromium...")

            # Use launch_persistent_context for better profile management
            # This replaces the deprecated --user-data-dir argument approach
            context: BrowserContext = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=True,
                args=[
                    "--disable-pdf-extension",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
            )
            logger.info("[Browser] ✓ Chromium launched successfully")

            page: Page = context.new_page()
            logger.debug("[Browser] New page created")

            try:
                yield p, context.browser, context, page
            except Exception as e:
                logger.error(f"[Browser] Error during page operations: {e}", exc_info=True)
                raise
            finally:
                try:
                    page.close()
                    logger.debug("[Browser] Page closed")
                except Exception as e:
                    logger.warning(f"[Browser] Error closing page: {e}")

                try:
                    context.close()
                    logger.debug("[Browser] Context closed")
                except Exception as e:
                    logger.warning(f"[Browser] Error closing context: {e}")
    except Exception as e:
        logger.error(f"[Browser] Failed to launch Chromium: {e}", exc_info=True)
        raise
