# journal_club/browser.py
import os
import json
import logging
import subprocess
import time
import socket
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
    """
    Try to find system Chrome. If not found, Playwright's bundled Chromium will be used instead.
    This function is kept for backwards compatibility but failures are non-fatal.
    """
    if override and os.path.exists(override):
        return override
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None  # Return None instead of raising — Playwright will use bundled Chromium


def _ensure_pdf_download_preference(profile_dir: str) -> None:
    """
    Set Chrome's 'always_open_pdf_externally' preference so PDFs are downloaded
    rather than opened in Chrome's built-in PDF viewer.
    """
    prefs_path = os.path.join(profile_dir, "Default", "Preferences")
    try:
        os.makedirs(os.path.dirname(prefs_path), exist_ok=True)
        username = os.environ.get("USERNAME", "Users")
        default_dir = os.path.dirname(prefs_path)
        subprocess.run(
            ["icacls", default_dir, "/grant", f"{username}:(F)", "/T", "/Q"],
            capture_output=True, timeout=10,
        )
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
    Tell Chrome (via CDP) to save all downloads to *download_dir*.
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


def _kill_chrome_with_profile(profile_dir: str) -> None:
    """Kill Chrome process trees that are using profile_dir.

    Finds parent chrome.exe processes whose command line contains the profile
    directory name, then uses `taskkill /F /T` to terminate each one along
    with all its children (renderer, GPU, utility processes — these don't have
    the profile path in their own command lines so PowerShell alone misses them).
    """
    profile_name = os.path.basename(os.path.normpath(profile_dir))
    try:
        # Find parent Chrome PIDs by profile name, then kill each process tree
        ps_cmd = (
            f"$pids = (Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" "
            f"| Where-Object {{$_.CommandLine -like '*{profile_name}*'}}).ProcessId; "
            f"if ($pids) {{"
            f"  $pids | ForEach-Object {{ "
            f"    & taskkill /F /T /PID $_ 2>$null "
            f"  }}; "
            f"  Start-Sleep -Milliseconds 1200 "
            f"}}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, timeout=15,
        )
        logger.info(f"[Browser] Killed any stale Chrome process trees for '{profile_name}'")
    except Exception as e:
        logger.debug(f"[Browser] Could not kill stale Chrome processes: {e}")


def _cleanup_chromium_locks(profile_dir: str) -> None:
    """Kill stale Chrome sessions and remove their lock files."""
    _kill_chrome_with_profile(profile_dir)

    # Grant current user full control of Default/ so LOCK is deletable.
    # Chrome sets restrictive ACLs on its lock file that survive process death.
    default_dir = os.path.join(profile_dir, "Default")
    if os.path.exists(default_dir):
        try:
            username = os.environ.get("USERNAME") or os.environ.get("USER") or "Users"
            subprocess.run(
                ["icacls", default_dir, "/grant", f"{username}:(F)", "/T", "/Q"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    lock_files = [
        os.path.join(profile_dir, "SingletonLock"),
        os.path.join(profile_dir, "SingletonCookie"),
        os.path.join(profile_dir, "SingletonSocket"),
        os.path.join(profile_dir, "lockfile"),
        os.path.join(profile_dir, "Default", "LOCK"),
    ]
    for path in lock_files:
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"[Browser] Removed stale lock file: {path}")
            except Exception as e:
                logger.warning(f"[Browser] Could not remove lock file {path}: {e}")


def _find_free_port() -> int:
    """Find a free TCP port for Chrome's debugging interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def launch_browser(profile_dir: str, chrome_path: str = "", port: int = 0,
                   start_url: str = "about:blank"):
    """
    Launch Playwright's bundled Chromium browser.

    Uses a fresh temporary profile for each session to avoid lock files and permission issues.
    No system Chrome dependency — works on local machines, Render, Docker, and containers.

    Yields (playwright, browser, context, page). Cleans up on exit.
    """
    import shutil
    import tempfile

    # Kill any stale processes (best effort)
    if profile_dir:
        try:
            os.makedirs(profile_dir, exist_ok=True)
            _cleanup_chromium_locks(profile_dir)
        except Exception:
            pass  # non-fatal

    # Create a temporary profile for this session
    temp_profile = tempfile.mkdtemp(prefix="jc-chrome-")
    logger.info(f"[Browser] Using temp profile: {temp_profile}")

    try:
        with sync_playwright() as p:
            # Use Playwright's bundled Chromium (no system dependency needed)
            logger.info("[Browser] Launching Playwright's bundled Chromium")
            browser: Browser = p.chromium.launch(
                headless=False,  # visible window helps with debugging
                args=[
                    f"--user-data-dir={temp_profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-pdf-extension",
                    "--disable-popup-blocking",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            logger.info("[Browser] ✓ Chromium launched")

            context: BrowserContext = browser.new_context()

            # Minimal stealth — only patch navigator.webdriver
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            logger.info("[Browser] ✓ Stealth script injected")

            page: Page = context.new_page()
            if start_url != "about:blank":
                page.goto(start_url, wait_until="domcontentloaded")
            logger.info("[Browser] ✓ Page created")

            try:
                yield p, browser, context, page
            except Exception as e:
                logger.error(f"[Browser] Error during page operations: {e}", exc_info=True)
                raise
            finally:
                try:
                    page.close()
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
                shutil.rmtree(temp_profile, ignore_errors=True)
                logger.info("[Browser] Closed and cleaned up temp profile")
    except Exception as e:
        logger.error(f"[Browser] Error launching Chromium: {e}")
        shutil.rmtree(temp_profile, ignore_errors=True)
        raise
        logger.debug(f"[Browser] Temp profile removed")
