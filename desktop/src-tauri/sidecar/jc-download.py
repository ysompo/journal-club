#!/usr/bin/env python3
"""
Journal Club download sidecar.

Reads one JSON object from stdin:
{
  "input":         "<PMID | DOI | URL>",
  "queue_item_id": "<uuid>",
  "device_id":     "<uuid>",
  "api_url":       "https://...",
  "token":         "<JWT>",
  "huji_email":    "user@mail.huji.ac.il",
  "huji_password": "...",
  "chrome_profile": "/path/to/profile",
  "chrome_path":   "",          // optional
  "output_dir":    "/tmp/jc",   // temp dir for PDFs during download
  "browsers_dir":  "<app data>/browsers"  // persistent Playwright cache
}

Writes JSON-lines to stdout:
  {"type": "progress", "message": "..."}
  {"type": "metadata", "article": {...}}   // after resolver completes
  {"type": "done",     "article_id": "..."}
  {"type": "error",    "message": "...", "step": "..."}

Exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import sys
import json
import os
import subprocess
import tempfile
import traceback

# Disable Python output buffering as early as possible so a killed sidecar
# leaves a complete log up to the last printed line.
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# ── Path setup: find the journal_club package ─────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Sidecar lives at desktop/src-tauri/sidecar/ → go up 3 to repo root
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
sys.path.insert(0, _REPO_ROOT)


import requests as _req


def _emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def _ensure_chromium(browsers_dir: str) -> None:
    """Ensure Playwright's Chromium is installed in ``browsers_dir``.

    Uses a persistent, per-user cache so the ~170 MB browser is downloaded
    exactly once on first run and reused across app updates. Must be called
    BEFORE any ``playwright`` import that triggers browser launch, and the
    env var stays set for the remainder of the process.
    """
    # Writability / space sanity check — surfaces corporate-lockdown or
    # quota issues with an actionable message instead of a cryptic WinError.
    try:
        os.makedirs(browsers_dir, exist_ok=True)
    except OSError as e:
        raise RuntimeError(
            f"Cannot create browser cache at {browsers_dir}: {e}. "
            f"Check that the folder is writable."
        )
    if not os.access(browsers_dir, os.W_OK):
        raise RuntimeError(
            f"Browser cache at {browsers_dir} is not writable. "
            f"Check folder permissions."
        )
    try:
        import shutil as _shutil
        free_bytes = _shutil.disk_usage(browsers_dir).free
        if free_bytes < 500 * 1024 * 1024:  # 500 MB headroom
            raise RuntimeError(
                f"Not enough disk space for browser download "
                f"({free_bytes // (1024 * 1024)} MB free, need ~500 MB)."
            )
    except OSError:
        pass  # disk_usage unsupported; skip check

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_dir

    # Sentinel marker written only after a successful install completes.
    # Using a marker instead of directory presence guards against partial
    # installs left behind by killed processes or failed network transfers.
    sentinel = os.path.join(browsers_dir, ".jc_install_complete")
    if os.path.exists(sentinel):
        return

    # Clean up any half-written browser directories from a previous crash so
    # Playwright's installer starts fresh and can verify SHA-256 cleanly.
    try:
        for name in os.listdir(browsers_dir):
            if name.startswith("chromium_headless_shell-") or name.startswith("chromium-"):
                import shutil as _shutil
                _shutil.rmtree(os.path.join(browsers_dir, name), ignore_errors=True)
    except OSError:
        pass

    _emit({"type": "progress", "message": "First-time setup: downloading browser (~170 MB)…"})

    # Invoke the bundled Playwright node driver directly. This avoids reliance
    # on a ``playwright`` CLI on PATH and works inside a PyInstaller one-file
    # bundle where ``python -m playwright`` is not available.
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
    except ImportError as e:
        # Private API moved/renamed in a future Playwright release. Surface a
        # clear error with the version so we can diagnose quickly.
        try:
            import playwright as _pw
            ver = getattr(_pw, "__version__", "unknown")
        except Exception:
            ver = "unknown"
        raise RuntimeError(
            f"Playwright internal driver API missing (version={ver}): {e}. "
            f"Reinstall the app."
        )
    driver_executable, driver_cli = compute_driver_executable()
    env = get_driver_env()
    env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_dir

    # IMPORTANT: never use ``capture_output=True`` here. The install downloads
    # ~170 MB and the node driver can write verbose progress to stderr; a
    # fixed OS pipe (~64 KB on Windows) can fill and deadlock the child on
    # write while we block on wait. Use temp files + a hard timeout instead.
    with tempfile.TemporaryFile(mode="w+") as stderr_f:
        try:
            proc = subprocess.run(
                [driver_executable, *driver_cli, "install", "chromium"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=stderr_f,
                timeout=600,  # 10 min — generous even on slow connections
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Browser download timed out after 10 minutes. "
                "Check your network connection and retry."
            )
        if proc.returncode != 0:
            stderr_f.seek(0)
            tail = stderr_f.read()[-2000:].strip()
            raise RuntimeError(
                f"Playwright install failed (exit {proc.returncode}): {tail}"
            )

    # Atomically mark the install as complete AFTER subprocess returns 0.
    with open(sentinel, "w") as f:
        f.write("ok")
    _emit({"type": "progress", "message": "Browser installed."})


from journal_club.config import Config
from journal_club.resolver import resolve
from journal_club.router import detect_publisher


def _post(url: str, token: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    r = _req.post(url, headers=headers, **kwargs)
    r.raise_for_status()
    return r.json()


def _get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class _Tee:
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
        return len(data) if isinstance(data, str) else 0
    def flush(self):
        for s in self._streams:
            try: s.flush()
            except Exception: pass


_LOG_PATH: str = ""


def _setup_log(queue_item_id: str) -> str:
    log_dir = os.path.join(tempfile.gettempdir(), "jc_downloads", "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"sidecar-{queue_item_id}.log")
    # buffering=1 → line-buffered so each newline flushes to disk immediately,
    # so a crashed/killed sidecar still leaves a complete log up to the last line.
    fh = open(path, "w", encoding="utf-8", errors="replace", buffering=1)
    # Force underlying stdout/stderr to line-buffered too, so prints from the
    # original streams flush at every newline before being teed.
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    sys.stderr = _Tee(sys.stderr, fh)
    sys.stdout = _Tee(sys.stdout, fh)
    return path


def main() -> int:
    # Tauri's shell sidecar API doesn't close stdin after writing, so we'd
    # block forever on read(). The caller appends a newline; readline() returns
    # as soon as the JSON config arrives.
    raw = sys.stdin.readline()
    try:
        cmd = json.loads(raw)
    except json.JSONDecodeError as e:
        _emit({"type": "error", "message": f"Invalid stdin JSON: {e}", "step": "init"})
        return 1

    global _LOG_PATH
    try:
        _LOG_PATH = _setup_log(cmd.get("queue_item_id", "unknown"))
        _emit({"type": "progress", "message": f"Log: {_LOG_PATH}"})
    except Exception:
        pass

    api_url = cmd["api_url"].rstrip("/")
    token = cmd["token"]
    queue_item_id = cmd["queue_item_id"]
    device_id = cmd["device_id"]
    input_str = cmd["input"]

    cfg = Config(
        huji_email=cmd["huji_email"],
        huji_password=cmd["huji_password"],
        output_dir=cmd.get("output_dir") or tempfile.mkdtemp(prefix="jc_"),
        # chrome_profile is intentionally ignored: browser.py uses a dedicated
        # JC profile under %LOCALAPPDATA%\JournalClub\chrome-profile.
        chrome_profile="",
        chrome_path=cmd.get("chrome_path", ""),
    )

    # ── Ensure Playwright Chromium is present (downloaded on first run) ───────
    browsers_dir = cmd.get("browsers_dir")
    if not browsers_dir:
        _emit({"type": "error", "message": "browsers_dir not provided by host", "step": "init"})
        return 1
    try:
        _ensure_chromium(browsers_dir)
    except Exception as e:
        _emit({"type": "error", "message": f"Browser setup failed: {e}", "step": "install_browser"})
        return 1

    # Import download module AFTER PLAYWRIGHT_BROWSERS_PATH is set, so the
    # sync_playwright() context picks up the correct browser location.
    from download import download_article

    # ── Download ──────────────────────────────────────────────────────────────
    # NOTE: Desktop (useQueuePoller) already claims the item before spawning this
    # sidecar. No second claim needed here.
    try:
        _emit({"type": "progress", "message": f"Resolving: {input_str}"})
        meta, pdf_path = download_article(input_str, cfg)
    except Exception as e:
        err_msg = str(e)
        _emit({"type": "progress", "message": f"Download failed: {err_msg}"})
        log_content = ""
        if _LOG_PATH:
            try:
                with open(_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    log_content = f.read()
            except Exception:
                pass
        try:
            _post(f"{api_url}/queue/{queue_item_id}/failed", token,
                  json={"error": err_msg, "error_step": "download",
                        "publisher": "", "log_content": log_content})
        except Exception:
            pass
        full_msg = f"{err_msg}\n\nFull log: {_LOG_PATH}" if _LOG_PATH else err_msg
        _emit({"type": "error", "message": full_msg, "step": "download"})
        return 1

    # ── Emit metadata so UI can show article title immediately ────────────────
    article_payload = {
        "title": meta.title or input_str[:120],
        "authors": meta.authors,
        "journal": meta.journal or "",
        "year": int(meta.pub_date[:4]) if meta.pub_date and meta.pub_date[:4].isdigit() else None,
        "doi": meta.doi,
        "url": meta.url,
        "abstract": meta.abstract or None,
        "pmid": meta.pmid,
        "volume": None,
        "issue": None,
        "pages": None,
        "pub_date": meta.pub_date or None,
        "keywords": [],
        "mesh_terms": [],
    }
    _emit({"type": "metadata", "article": article_payload})

    # ── POST article to backend ───────────────────────────────────────────────
    try:
        _emit({"type": "progress", "message": "Saving article to server…"})
        article_resp = _post(f"{api_url}/articles/", token, json=article_payload)
        article_id = article_resp["id"]
    except Exception as e:
        _emit({"type": "error", "message": str(e), "step": "create_article"})
        try:
            _post(f"{api_url}/queue/{queue_item_id}/failed", token,
                  json={"error": str(e), "error_step": "create_article", "publisher": ""})
        except Exception:
            pass
        return 1

    # ── Upload PDF ────────────────────────────────────────────────────────────
    try:
        _emit({"type": "progress", "message": "Uploading PDF…"})
        with open(pdf_path, "rb") as fh:
            resp = _req.post(
                f"{api_url}/articles/{article_id}/pdf",
                headers=_get_headers(token),
                files={"file": (f"{article_id}.pdf", fh, "application/pdf")},
            )
            resp.raise_for_status()
    except Exception as e:
        _emit({"type": "error", "message": str(e), "step": "upload_pdf"})
        try:
            _post(f"{api_url}/queue/{queue_item_id}/failed", token,
                  json={"error": str(e), "error_step": "upload_pdf", "publisher": ""})
        except Exception:
            pass
        return 1
    finally:
        # Clean up temp PDF regardless
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception:
            pass

    # ── Mark queue item done ──────────────────────────────────────────────────
    try:
        _post(f"{api_url}/queue/{queue_item_id}/done", token,
              json={"article_id": article_id})
    except Exception as e:
        # Non-fatal — PDF is uploaded, article created
        _emit({"type": "progress", "message": f"Warning: could not mark done: {e}"})

    _emit({"type": "done", "article_id": article_id})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        _emit({"type": "error", "message": traceback.format_exc(), "step": "uncaught"})
        sys.exit(1)
