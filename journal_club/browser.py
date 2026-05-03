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


# Profile subpaths whose mutations (cookies, encryption keys, login state)
# we want to persist back from the per-job clone to the master profile.
_PERSIST_PATHS = [
    "Local State",
    os.path.join("Default", "Cookies"),
    os.path.join("Default", "Cookies-journal"),
    os.path.join("Default", "Network", "Cookies"),
    os.path.join("Default", "Network", "Cookies-journal"),
    os.path.join("Default", "Login Data"),
    os.path.join("Default", "Preferences"),
]

# Skip these on clone — large transient caches add seconds to the copy.
# We also skip Sessions/* and Current/Last Tabs/Session files so Chrome doesn't
# auto-restore stale tabs (e.g. a leftover sciencedirect PDF) into every job.
_CLONE_IGNORE = {
    "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache",
    "Service Worker", "DawnGraphiteCache", "DawnWebGPUCache",
    "Crashpad", "BrowserMetrics", "Storage",
    "Sessions",
    "Current Tabs", "Current Session", "Last Tabs", "Last Session",
    # Extensions hijack PDF downloads (Adobe Acrobat etc) — never clone them
    "Extensions", "Extension Rules", "Extension Scripts", "Extension State",
    "Local Extension Settings", "Managed Extension Settings",
    "Sync Extension Settings",
}


def _clone_profile(src: str, dst: str) -> None:
    """Shallow-copy the JC master profile to dst, skipping bulky caches and
    session-restore files."""
    import shutil
    if not os.path.exists(src):
        return
    def _ignore(_dir, names):
        return [n for n in names if n in _CLONE_IGNORE]
    shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=True)
    # Belt-and-suspenders: even if a Sessions file slipped through, nuke it.
    default_dir = os.path.join(dst, "Default")
    for rel in ("Current Tabs", "Current Session", "Last Tabs", "Last Session"):
        try:
            p = os.path.join(default_dir, rel)
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    sessions_dir = os.path.join(default_dir, "Sessions")
    if os.path.isdir(sessions_dir):
        try:
            shutil.rmtree(sessions_dir, ignore_errors=True)
        except Exception:
            pass


def _persist_profile(src: str, dst: str) -> None:
    """Copy auth-relevant files from the per-job clone back to master."""
    import shutil
    for rel in _PERSIST_PATHS:
        s = os.path.join(src, rel)
        if not os.path.exists(s):
            continue
        d = os.path.join(dst, rel)
        try:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
        except Exception as e:
            logger.debug(f"[Browser] persist {rel}: {e}")


def _mark_profile_clean_exit(profile_dir: str) -> None:
    """Rewrite Preferences so Chrome doesn't show the 'Restore pages?' bubble.

    When a Chrome session is killed (lockfile collision, taskkill), Preferences
    keeps `exit_type: "Crashed"`. On next launch the crash-restore bubble blocks
    HUJI auto-fill. Resetting to a clean exit suppresses it.
    """
    prefs_path = os.path.join(profile_dir, "Default", "Preferences")
    if not os.path.exists(prefs_path):
        return
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            prefs = json.load(f)
        profile = prefs.setdefault("profile", {})
        profile["exit_type"] = "Normal"
        profile["exited_cleanly"] = True
        # Force "open new tab" startup; clear any pinned restore URLs so a
        # stale sciencedirect tab can't reappear on next launch.
        session = prefs.setdefault("session", {})
        session["restore_on_startup"] = 5  # 5 = open new tab page
        session["urls_to_restore_on_startup"] = []
        session["startup_urls"] = []
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception as e:
        logger.debug(f"[Browser] could not mark profile clean: {e}")


def _wait_for_profile_unlock(profile_dir: str, timeout: float = 3.0) -> bool:
    """Poll until the SQLite Cookies file is openable for write (or timeout).

    On Windows, killing chrome.exe doesn't immediately release file handles;
    cloning while a handle is still held copies an empty/locked file. We retry
    a brief read+write probe on Cookies-journal until it succeeds or we hit
    the deadline.
    """
    target = os.path.join(profile_dir, "Default", "Network", "Cookies-journal")
    if not os.path.exists(target):
        # Nothing to wait for — caller can clone immediately.
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(target, "rb"):
                pass
            with open(target, "ab"):
                pass
            return True
        except OSError:
            time.sleep(0.15)
    return False


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


def _seed_profile_from_real_chrome(active_profile: str) -> None:
    """One-time copy of cookies/login state from the user's real Chrome profile.

    Runs only if active_profile/Default/Cookies doesn't exist yet (first launch).
    Requires the user's real Chrome to be CLOSED — otherwise Cookies SQLite is
    locked and the copy fails per file.
    """
    import shutil
    marker = os.path.join(active_profile, "Default", "Cookies")
    if os.path.exists(marker):
        return  # already seeded

    real_root = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    if not os.path.isdir(real_root):
        logger.info(f"[Browser] No real Chrome profile found at {real_root}, skipping seed")
        return

    src_default = os.path.join(real_root, "Default")
    dst_default = os.path.join(active_profile, "Default")
    os.makedirs(dst_default, exist_ok=True)

    # Critical files for session/cookie inheritance. Cache, history, etc. are
    # intentionally skipped — they bloat the copy and aren't needed for auth.
    files = [
        ("Default", "Cookies"),
        ("Default", "Cookies-journal"),
        ("Default", "Login Data"),
        ("Default", "Login Data-journal"),
        ("Default", "Web Data"),
        ("Default", "Web Data-journal"),
        ("Default", "Preferences"),
        ("Default", "Network", "Cookies"),
        ("Default", "Network", "Cookies-journal"),
        # Local State holds the encryption key for Cookies — required for
        # cookies to decrypt under the same user.
        ("Local State",),
    ]
    failed = []
    copied = 0
    for parts in files:
        src = os.path.join(real_root, *parts)
        dst = os.path.join(active_profile, *parts)
        if not os.path.exists(src):
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        except (PermissionError, OSError) as e:
            failed.append((parts[-1], str(e)))

    if failed:
        print(f"   [Browser] Profile seed: copied {copied}, failed {len(failed)}")
        print(f"   [Browser] If Chrome is open, close it once so Cookies can be copied:")
        for name, err in failed[:3]:
            print(f"     - {name}: {err}")
    else:
        print(f"   [Browser] ✓ Seeded JC profile from real Chrome ({copied} files)")


def _find_free_port() -> int:
    """Find a free TCP port for Chrome's debugging interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_cdp(port: int, timeout: float = 20.0) -> None:
    """Block until Chrome's DevTools port is accepting connections."""
    import urllib.request
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.0) as r:
                if r.status == 200:
                    return
        except Exception as e:
            last_err = e
            time.sleep(0.25)
    raise RuntimeError(f"Chrome DevTools port {port} not ready after {timeout}s ({last_err})")


def _spawn_chrome_with_cdp(chrome_path: str, profile_dir: str, port: int,
                           start_url: str = "about:blank") -> subprocess.Popen:
    """Spawn user-visible Chrome with a remote debugging port.

    Always launches with about:blank — passing a target URL on the command line
    interacts badly with cloned profiles (occasionally re-triggers session
    restore). The auth flow does its own page.goto() once attached.
    """
    _mark_profile_clean_exit(profile_dir)
    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-crash-restore-bubble",
        "--disable-features=TranslateUI,Translate,InfiniteSessionRestore",
        "--disable-popup-blocking",
        "--disable-translate",
        "--restore-last-session=false",
        # Disable all extensions — third-party extensions (Adobe Acrobat,
        # Endnote Click, Kopernio, ad blockers) intercept PDF downloads
        # and replace the page with their own UI, breaking the flow.
        "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disable-extensions-http-throttling",
        # Block any extension install attempts (Web Store, sync, enterprise)
        "--disable-extensions-except=",
        "--disable-default-apps",
        "--disable-sync",
        "about:blank",
    ]
    creationflags = 0
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP so Ctrl+C in sidecar doesn't propagate.
        creationflags = 0x00000200
    return subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


@contextmanager
def launch_browser(profile_dir: str, chrome_path: str = "", port: int = 0,
                   start_url: str = "about:blank"):
    """
    Launch a JC-owned Chrome via CDP attach.

    Strategy: spawn the user's real Chrome with a dedicated persistent profile
    and remote debugging port, then attach Playwright via CDP. This avoids
    Playwright's launch fingerprint that ScienceDirect blocks.

    First run: HUJI login required (empty profile). Subsequent runs reuse the
    cookies stored in the JC profile.

    Falls back to bundled Chromium if no system Chrome is available.

    Yields (playwright, browser, context, page).
    """
    import shutil
    import tempfile

    if not chrome_path:
        chrome_path = find_chrome() or ""
    use_real_chrome = bool(chrome_path) and os.path.exists(chrome_path)

    chrome_proc: subprocess.Popen | None = None
    temp_profile: str | None = None
    master_profile: str | None = None

    if use_real_chrome:
        # Dedicated JC profile under LocalAppData so HUJI cookies persist
        # across app updates and don't conflict with the user's real Chrome.
        if profile_dir:
            master_profile = profile_dir
        else:
            local_appdata = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            master_profile = os.path.join(local_appdata, "JournalClub", "chrome-profile")
        os.makedirs(master_profile, exist_ok=True)

        # Clone the master profile to a per-job temp dir so concurrent
        # downloads can't collide on Chrome's SingletonLock / lockfile.
        # We copy back the cookie stores at the end to preserve session.
        temp_profile = tempfile.mkdtemp(prefix="jc-chrome-job-")
        active_profile = temp_profile
        # Kill any stale Chrome holding the master profile open — otherwise
        # Cookies/Sessions files are locked and the clone copies an empty
        # profile, which loses the PDF-download preference and forces Chrome
        # to open PDFs in its built-in viewer instead of triggering downloads.
        try:
            _kill_chrome_with_profile(master_profile)
        except Exception:
            pass
        # Wait briefly for Windows to release the SQLite handles before cloning
        # — otherwise WinError 32 leaves us with an empty profile.
        try:
            if not _wait_for_profile_unlock(master_profile, timeout=3.0):
                logger.warning("[Browser] master profile still locked after 3s, cloning anyway")
        except Exception:
            pass
        try:
            _clone_profile(master_profile, active_profile)
        except Exception as e:
            logger.warning(f"[Browser] profile clone failed, using empty profile: {e}")
        try:
            _cleanup_chromium_locks(active_profile)
        except Exception:
            pass
        _ensure_pdf_download_preference(active_profile)
        logger.info(f"[Browser] CDP attach: Chrome={chrome_path} cloned profile={active_profile}")
    else:
        temp_profile = tempfile.mkdtemp(prefix="jc-chrome-")
        active_profile = temp_profile
        logger.info(f"[Browser] Using bundled Chromium with temp profile: {active_profile}")

    try:
        with sync_playwright() as p:
            if use_real_chrome:
                cdp_port = port or _find_free_port()
                print(f"   [Browser] Spawning Chrome on CDP port {cdp_port}...")
                chrome_proc = _spawn_chrome_with_cdp(chrome_path, active_profile, cdp_port, start_url)
                # Emit PID + profile so the Tauri host can kill Chrome if the
                # sidecar is force-terminated (Python finally blocks won't run).
                print(json.dumps({"type": "chrome_pid", "pid": chrome_proc.pid,
                                  "profile": active_profile}), flush=True)
                _wait_for_cdp(cdp_port)
                browser: Browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                # Persistent profile gives us a default context already.
                contexts = browser.contexts
                context: BrowserContext = contexts[0] if contexts else browser.new_context()
                pages = context.pages
                page: Page = pages[0] if pages else context.new_page()
                if start_url != "about:blank" and page.url in ("about:blank", "chrome://newtab/", ""):
                    page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
                logger.info("[Browser] ✓ CDP attached")
            else:
                launch_kwargs = {
                    "user_data_dir": active_profile,
                    "headless": True,
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/145.0.7632.6 Safari/537.36"
                    ),
                    "args": [
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-pdf-extension",
                        "--disable-popup-blocking",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-extensions",
                        "--mute-audio",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--js-flags=--max-old-space-size=128",
                    ],
                }
                context = p.chromium.launch_persistent_context(**launch_kwargs)
                browser = context.browser
                if not browser:
                    raise RuntimeError("Browser context created but browser not accessible")
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                page = context.new_page()
                if start_url != "about:blank":
                    page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)

            try:
                yield p, browser, context, page
            except Exception as e:
                logger.error(f"[Browser] Error during page operations: {e}", exc_info=True)
                raise
            finally:
                try:
                    if not use_real_chrome:
                        # Only close pages/context for the launched (bundled) flow.
                        # For CDP attach, closing the context kills the user's Chrome window
                        # awkwardly — terminate the process below instead.
                        try: page.close()
                        except Exception: pass
                        try: context.close()
                        except Exception: pass
                        try: browser.close()
                        except Exception: pass
                except Exception:
                    pass
    finally:
        if chrome_proc is not None:
            try:
                # taskkill /F /T kills the full process tree (renderer, GPU, utility).
                # terminate() only sends SIGTERM to the parent and orphans children on Windows.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(chrome_proc.pid)],
                    capture_output=True, timeout=10,
                )
            except Exception:
                try:
                    chrome_proc.kill()
                except Exception:
                    pass
            # Belt-and-suspenders: kill any chrome.exe still referencing this profile.
            try:
                _kill_chrome_with_profile(active_profile)
            except Exception:
                pass
        if use_real_chrome and master_profile and temp_profile:
            try:
                _persist_profile(temp_profile, master_profile)
            except Exception as e:
                logger.warning(f"[Browser] persist back failed: {e}")
            # Belt-and-suspenders: kill any chrome.exe still holding either the
            # active clone OR the master profile, so the next download starts clean.
            try:
                _kill_chrome_with_profile(master_profile)
            except Exception:
                pass
        if temp_profile:
            shutil.rmtree(temp_profile, ignore_errors=True)
        logger.info("[Browser] Cleanup complete")
