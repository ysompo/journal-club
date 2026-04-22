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
  "output_dir":    "/tmp/jc"   // temp dir for PDFs during download
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
import tempfile
import traceback

# ── Path setup: find the journal_club package ─────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Sidecar lives at desktop/src-tauri/sidecar/ → go up 3 to repo root
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
sys.path.insert(0, _REPO_ROOT)

# ── When frozen by PyInstaller, point Playwright to bundled browsers ──────────
if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(sys._MEIPASS, "pw-browsers")

import requests as _req
from journal_club.config import Config
from journal_club.resolver import resolve
from journal_club.router import detect_publisher
from download import download_article


def _emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def _post(url: str, token: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    r = _req.post(url, headers=headers, **kwargs)
    r.raise_for_status()
    return r.json()


def _get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    raw = sys.stdin.read()
    try:
        cmd = json.loads(raw)
    except json.JSONDecodeError as e:
        _emit({"type": "error", "message": f"Invalid stdin JSON: {e}", "step": "init"})
        return 1

    api_url = cmd["api_url"].rstrip("/")
    token = cmd["token"]
    queue_item_id = cmd["queue_item_id"]
    device_id = cmd["device_id"]
    input_str = cmd["input"]

    cfg = Config(
        huji_email=cmd["huji_email"],
        huji_password=cmd["huji_password"],
        output_dir=cmd.get("output_dir") or tempfile.mkdtemp(prefix="jc_"),
        chrome_profile=cmd.get("chrome_profile", ""),
        chrome_path=cmd.get("chrome_path", ""),
    )

    # ── Download ──────────────────────────────────────────────────────────────
    # NOTE: Desktop (useQueuePoller) already claims the item before spawning this
    # sidecar. No second claim needed here.
    try:
        _emit({"type": "progress", "message": f"Resolving: {input_str}"})
        meta, pdf_path = download_article(input_str, cfg)
    except Exception as e:
        err_msg = str(e)
        _emit({"type": "progress", "message": f"Download failed: {err_msg}"})
        try:
            _post(f"{api_url}/queue/{queue_item_id}/failed", token,
                  json={"error": err_msg, "error_step": "download", "publisher": ""})
        except Exception:
            pass
        _emit({"type": "error", "message": err_msg, "step": "download"})
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
