#!/usr/bin/env python3
"""
Journal Club — Flask web app
Usage: python app.py
Then open http://localhost:5000
"""
from __future__ import annotations

import threading
import logging
from logging.handlers import RotatingFileHandler

import functools
import secrets

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from apscheduler.schedulers.background import BackgroundScheduler

from journal_club.config import Config, load_config
from journal_club.resolver import resolve
from journal_club.journals_catalog import CATALOG
from journal_club.toc_scraper import scrape
from journal_club.mailer import send_reading_list
from journal_club.logging_config import configure_logging
import journal_club.storage as storage

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)   # ephemeral — sessions reset on restart (fine for local use)

# Support deployment behind a reverse proxy at /tools/journal-club
import os
script_name = os.environ.get("SCRIPT_NAME", "")
if script_name:
    app.config["APPLICATION_ROOT"] = script_name

cfg = load_config("config.yaml")

# Ensure output directory exists
if cfg.output_dir:
    try:
        os.makedirs(cfg.output_dir, exist_ok=True)
    except Exception as e:
        pass  # log warning below after logging is configured

# Configure logging: set DEBUG=1 env var for verbose debugging
debug_mode = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
log_level = logging.DEBUG if debug_mode else logging.INFO
log_file = "journal_club.log" if not app.debug else None  # log to file in production

configure_logging(log_level=log_level, log_file=log_file)
app.logger.info(f"Journal Club started (debug={debug_mode}, log_level={logging.getLevelName(log_level)})")

# Log output directory
if cfg.output_dir:
    try:
        if os.path.isdir(cfg.output_dir):
            app.logger.info(f"Output directory: {cfg.output_dir}")
        else:
            app.logger.error(f"Output directory not accessible: {cfg.output_dir}")
    except Exception as e:
        app.logger.error(f"Error checking output directory: {e}")


def require_admin(f):
    """Decorator: redirect to /admin/login if not authenticated as admin."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return wrapper



def get_runtime_config() -> Config:
    """Return Config with DB settings overriding config.yaml values where set."""
    s = storage.get_all_settings()
    return Config(
        huji_email=s.get("huji_email") or cfg.huji_email,
        huji_password=s.get("huji_password") or cfg.huji_password,
        output_dir=cfg.output_dir,
        chrome_profile=cfg.chrome_profile,
        chrome_path=cfg.chrome_path,
        resend_api_key=s.get("resend_api_key") or cfg.resend_api_key,
        resend_from=s.get("resend_from") or cfg.resend_from,
        email_to_1=s.get("email_to_1") or cfg.email_to_1,
        email_to_2=s.get("email_to_2") or cfg.email_to_2,
        email_to_3=s.get("email_to_3") or cfg.email_to_3,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _refresh_journal(journal: dict) -> None:
    """Scrape TOC for a single journal and persist to DB. Safe to call in any thread."""
    try:
        catalog_entry = next(
            (e for e in CATALOG if e.toc_url == journal["toc_url"]),
            None,
        )
        publisher = catalog_entry.publisher if catalog_entry else "generic"
        days_per_issue = catalog_entry.days_per_issue if catalog_entry else 7
        issues_to_fetch = journal.get("issues_to_fetch") or 1
        result = scrape(
            publisher,
            journal["toc_url"],
            issn=journal.get("issn"),
            issues_to_fetch=issues_to_fetch,
            days_per_issue=days_per_issue,
        )
        old_label = journal.get("current_issue_label", "")
        is_new = bool(result.issue_label and result.issue_label != old_label)
        storage.update_journal_toc(journal["id"], result.issue_label, result.articles, is_new)
        print(f"[TOC] {journal['name']}: {len(result.articles)} articles. New={is_new}")
    except Exception as e:
        print(f"[TOC] Failed to refresh {journal['name']}: {e}")


def _refresh_all_journals() -> None:
    for j in storage.get_journals():
        _refresh_journal(j)


# ── Scheduler — weekly TOC refresh ───────────────────────────────────────────

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(_refresh_all_journals, "interval", weeks=1, id="weekly_toc_refresh")
scheduler.start()

# Only one browser-based download can run at a time (all downloads share port 9222)
_download_lock = threading.Lock()
# Dict so nested functions can mutate without 'global'; 'session' prevents a
# zombie thread from releasing a *new* download's lock after a force-release.
_download_lock_meta = {"acquired_at": None, "session": None, "article_id": None, "toc_article_id": None, "title": None}

# Queue for pending downloads when the lock is busy
_download_queue: list[dict] = []
_queue_lock = threading.Lock()
MAX_QUEUE = 15  # max items waiting (not counting the active download)

# ── Email job state ───────────────────────────────────────────────────────────
_email_job: dict = {
    "running": False,
    "status": "idle",       # idle | downloading | sending | done | failed
    "current": 0,           # articles downloaded so far in this job
    "total": 0,             # total articles to download in this job
    "attached": 0,          # PDFs attached in email
    "failed_count": 0,      # articles that failed to download
    "error": None,          # fatal error (send failure)
}
_email_job_lock = threading.Lock()


def _build_run(article_id, toc_article_id, meta, runtime_cfg, session_id):
    """Return the download thread function for a single article."""
    def _run():
        try:
            storage.set_download_error(article_id, "")
            if not runtime_cfg.huji_email or not runtime_cfg.huji_password:
                raise ValueError(
                    "HUJI credentials not configured — go to Settings to enter your email and password."
                )
            from download import download_article
            app.logger.info("[Download] Starting download for article_id=%s url=%s", article_id, meta.url)
            _, pdf_path = download_article(meta.url, runtime_cfg)
            storage.update_pdf_path(article_id, pdf_path)
            app.logger.info("[Download] Success article_id=%s pdf=%s", article_id, pdf_path)
            if toc_article_id:
                storage.link_reading_list_to_article(toc_article_id, article_id)
        except Exception as e:
            app.logger.error("[Download thread] article_id=%s error: %s", article_id, e, exc_info=True)
            # Safety net: the PDF may have been saved to disk before the exception
            # (e.g. Node.js EPIPE crash after successful on_download capture).
            # Chrome CDP downloads use the server-provided suggested filename, NOT
            # the slugified URL.  Scan output_dir for any PDF created in the last
            # 5 minutes that is a valid PDF file.
            try:
                import glob as _glob, time as _time
                _out = runtime_cfg.output_dir
                _now = _time.time()
                _candidates = []
                for _p in _glob.glob(os.path.join(_out, "*.pdf")):
                    try:
                        _age = _now - os.path.getmtime(_p)
                        _size = os.path.getsize(_p)
                        if _age < 300 and _size > 10_000:
                            _candidates.append((_age, _p))
                    except Exception:
                        pass
                # Pick the most recently modified PDF
                if _candidates:
                    _candidates.sort()
                    _, _found = _candidates[0]
                    with open(_found, "rb") as _f:
                        _header = _f.read(4)
                    if _header == b'%PDF':
                        app.logger.warning(
                            "[Download] Exception but valid PDF found on disk — treating as success: %s", _found
                        )
                        storage.update_pdf_path(article_id, _found)
                        if toc_article_id:
                            storage.link_reading_list_to_article(toc_article_id, article_id)
                        return   # skip set_download_error
                else:
                    app.logger.warning(
                        "[Download] No valid PDF found in recent files. Scanned: %s", _out
                    )
            except Exception as _check_err:
                app.logger.error("[Download] Disk-check failed: %s", _check_err)
            storage.set_download_error(article_id, str(e))
        finally:
            if _download_lock_meta["session"] == session_id:
                _download_lock_meta["acquired_at"] = None
                _download_lock_meta["session"] = None
                _download_lock_meta["article_id"] = None
                _download_lock_meta["toc_article_id"] = None
                _download_lock_meta["title"] = None
                _download_lock.release()
            _start_next_queued()
    return _run


def _start_next_queued():
    """Pop the next item from the queue and start its download. Call after releasing the lock."""
    import time as _t, uuid as _u
    with _queue_lock:
        if not _download_queue:
            return
        if not _download_lock.acquire(blocking=False):
            return  # another thread grabbed the lock first
        item = _download_queue.pop(0)
    sid = str(_u.uuid4())
    _download_lock_meta["acquired_at"] = _t.time()
    _download_lock_meta["session"] = sid
    _download_lock_meta["article_id"] = item["article_id"]
    _download_lock_meta["toc_article_id"] = item["toc_article_id"]
    _download_lock_meta["title"] = item["title"]
    threading.Thread(
        target=_build_run(item["article_id"], item["toc_article_id"], item["meta"], item["runtime_cfg"], sid),
        daemon=True,
    ).start()
    app.logger.info("[Download] Dequeued article_id=%s", item["article_id"])


def _run_email_job(items: list[dict], rc) -> None:
    """Download all undownloaded reading list articles, then send email. Runs in a daemon thread."""
    import time as _t, uuid as _u
    from journal_club.resolver import resolve as _resolve
    from download import download_article as _download_article

    to_addrs = [a for a in [rc.email_to_1, rc.email_to_2, rc.email_to_3] if a]
    failed: list[dict] = []

    undownloaded = [it for it in items if not it.get("pdf_path")]
    _email_job.update({"status": "downloading", "current": 0, "total": len(undownloaded)})

    for i, item in enumerate(undownloaded):
        _email_job["current"] = i + 1
        app.logger.info(
            "[EmailJob] Downloading %d/%d: %s", i + 1, len(undownloaded), item.get("title", "")[:60]
        )

        _download_lock.acquire(blocking=True)
        sid = str(_u.uuid4())
        _download_lock_meta.update({
            "acquired_at": _t.time(), "session": sid,
            "article_id": None, "toc_article_id": item.get("toc_article_id"),
            "title": item.get("title", ""),
        })
        try:
            meta = _resolve(item.get("doi") or item.get("url"))
            article_id = storage.save_article(meta, pdf_path=None)
            storage.set_download_error(article_id, "")
            _download_lock_meta["article_id"] = article_id
            _, pdf_path = _download_article(meta.url, rc)
            storage.update_pdf_path(article_id, pdf_path)
            storage.link_reading_list_to_article(item["toc_article_id"], article_id)
        except Exception as e:
            app.logger.error("[EmailJob] Download failed: %s — %s", item.get("title", ""), e)
            failed.append({"title": item.get("title", "Unknown"), "error": str(e)})
        finally:
            if _download_lock_meta["session"] == sid:
                _download_lock_meta.update({
                    "acquired_at": None, "session": None,
                    "article_id": None, "toc_article_id": None, "title": None,
                })
                _download_lock.release()
            _start_next_queued()

    # Send email with fresh item list (pdf_paths now populated)
    _email_job["status"] = "sending"
    fresh_items = storage.get_reading_list()
    try:
        attached = send_reading_list(
            articles=fresh_items,
            api_key=rc.resend_api_key,
            from_addr=rc.resend_from,
            to_addrs=to_addrs,
            failed=failed if failed else None,
        )
        storage.mark_reading_list_sent()
        _email_job.update({
            "status": "done", "error": None,
            "attached": attached, "failed_count": len(failed),
        })
        app.logger.info("[EmailJob] Done. %d PDFs attached, %d failed.", attached, len(failed))
    except Exception as e:
        app.logger.error("[EmailJob] Send failed: %s", e)
        _email_job.update({"status": "failed", "error": str(e)})
    finally:
        _email_job["running"] = False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("journals"))


@app.route("/add")
def add():
    return render_template("add_article.html", page="add")


@app.route("/history")
def history():
    articles = storage.get_history()
    return render_template("history.html", articles=articles, page="history")


@app.route("/bookmarks")
def bookmarks():
    articles = storage.get_bookmarks()
    return render_template("bookmarks.html", articles=articles, page="bookmarks")


@app.route("/article/<int:article_id>")
def article(article_id: int):
    a = storage.get_by_id(article_id)
    if a is None:
        return "Article not found", 404
    if request.headers.get("Accept") == "application/json":
        return jsonify(a)
    return render_template("article.html", article=a, page="history")


@app.route("/pdf/<int:article_id>")
def serve_pdf(article_id: int):
    """Serve the downloaded PDF file for an article."""
    a = storage.get_by_id(article_id)
    if a is None:
        return "Article not found", 404
    pdf_path = a.get("pdf_path")
    if not pdf_path:
        return "PDF not yet downloaded", 404
    import os
    if not os.path.exists(pdf_path):
        return "PDF file not found on disk", 404

    # Check if download is requested via query parameter
    download_param = request.args.get("download")
    as_attachment = download_param == "1"

    # Generate filename from title or use default
    filename = None
    if as_attachment:
        title = a.get("title", "article")
        # Clean title for filename (remove special characters)
        filename = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
        filename = filename.strip()[:100] or "article"  # Max 100 chars
        filename += ".pdf"

    return send_file(pdf_path, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


@app.route("/download", methods=["POST"])
def download():
    """
    Accept JSON {input: "<pmid | doi | url>", toc_article_id: <int|null>}.
    Resolves metadata immediately, saves a pending DB record, then either
    starts the download immediately or queues it if one is already running.
    Returns JSON {article_id, title, url, queued, position?}.
    """
    data = request.get_json(force=True)
    input_str = (data or {}).get("input", "").strip()
    toc_article_id = (data or {}).get("toc_article_id")
    if not input_str:
        return jsonify({"error": "No input provided"}), 400

    try:
        meta = resolve(input_str)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    import time, uuid
    # Force-release stale lock if held > 100s
    if _download_lock_meta["acquired_at"] and (time.time() - _download_lock_meta["acquired_at"]) > 100:
        app.logger.warning("[Download] Force-releasing stale lock (held > 100s)")
        _download_lock_meta["acquired_at"] = None
        _download_lock_meta["session"] = None
        try:
            _download_lock.release()
        except RuntimeError:
            pass

    try:
        article_id = storage.save_article(meta, pdf_path=None)
        runtime_cfg = get_runtime_config()
    except Exception as e:
        app.logger.error("Download setup failed: %s", e, exc_info=True)
        return jsonify({"error": f"Server error while preparing download: {e}"}), 500

    title = meta.title or meta.url

    if _download_lock.acquire(blocking=False):
        # Lock acquired — start immediately
        sid = str(uuid.uuid4())
        _download_lock_meta["acquired_at"] = time.time()
        _download_lock_meta["session"] = sid
        _download_lock_meta["article_id"] = article_id
        _download_lock_meta["toc_article_id"] = toc_article_id
        _download_lock_meta["title"] = title
        threading.Thread(
            target=_build_run(article_id, toc_article_id, meta, runtime_cfg, sid),
            daemon=True,
        ).start()
        return jsonify({"article_id": article_id, "title": title, "url": meta.url, "queued": False})
    else:
        # Lock busy — add to queue if space available
        with _queue_lock:
            if len(_download_queue) >= MAX_QUEUE:
                return jsonify({"error": f"Download queue is full ({MAX_QUEUE} items). Please wait."}), 429
            _download_queue.append({
                "article_id": article_id,
                "toc_article_id": toc_article_id,
                "meta": meta,
                "runtime_cfg": runtime_cfg,
                "title": title,
            })
            position = len(_download_queue)
        app.logger.info("[Download] Queued article_id=%s at position %s", article_id, position)
        return jsonify({"article_id": article_id, "title": title, "url": meta.url, "queued": True, "position": position})


@app.route("/download/status/<int:article_id>")
def download_status(article_id: int):
    """Poll this after /download to know when the PDF is ready."""
    art = storage.get_by_id(article_id)
    if not art:
        return jsonify({"status": "unknown"}), 404
    if art.get("pdf_path"):
        return jsonify({"status": "done", "article_id": article_id})
    if art.get("download_error"):
        return jsonify({"status": "failed", "error": art["download_error"]})
    return jsonify({"status": "downloading"})


@app.route("/download/report-error/<int:article_id>", methods=["POST"])
def report_download_error(article_id: int):
    """Send error report email for failed download."""
    art = storage.get_by_id(article_id)
    if not art:
        return jsonify({"success": False, "error": "Article not found"}), 404

    error_msg = art.get("download_error", "Unknown error")

    # Gather context: last 30 log lines
    log_lines = []
    try:
        with open("journal_club.log", "r", errors="ignore") as f:
            all_lines = f.readlines()
            log_lines = all_lines[-30:] if len(all_lines) > 30 else all_lines
    except Exception as e:
        log_lines = [f"Could not read logs: {e}"]

    # Build error report
    from datetime import datetime
    report = {
        "article_id": article_id,
        "title": art.get("title", "Unknown"),
        "doi": art.get("doi", "Unknown"),
        "url": art.get("url", "Unknown"),
        "error": error_msg,
        "timestamp": datetime.now().isoformat(),
        "logs": "".join(log_lines),
    }

    # Send email
    try:
        runtime_cfg = get_runtime_config()
        from journal_club.mailer import send_error_report
        send_error_report(report, runtime_cfg.resend_api_key)
        app.logger.info(f"[ErrorReport] Sent for article_id={article_id}")
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"[ErrorReport] Failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/download/active")
def download_active():
    """Return the currently active download and queue — used to restore UI state across page navigation."""
    article_id = _download_lock_meta.get("article_id")
    with _queue_lock:
        queued = [
            {"article_id": i["article_id"], "toc_article_id": i["toc_article_id"], "title": i["title"]}
            for i in _download_queue
        ]
    if not article_id or not _download_lock_meta.get("acquired_at"):
        return jsonify({"active": False, "queued": queued})
    return jsonify({
        "active": True,
        "article_id": article_id,
        "toc_article_id": _download_lock_meta.get("toc_article_id"),
        "title": _download_lock_meta.get("title") or "",
        "queued": queued,
    })


@app.route("/download/reset", methods=["POST"])
def download_reset():
    """Force-release the download lock and clear the queue. Use when a download is stuck."""
    held = _download_lock_meta["acquired_at"] is not None
    _download_lock_meta["acquired_at"] = None
    _download_lock_meta["session"] = None
    _download_lock_meta["article_id"] = None
    _download_lock_meta["toc_article_id"] = None
    _download_lock_meta["title"] = None
    with _queue_lock:
        queued_count = len(_download_queue)
        _download_queue.clear()
    if held:
        try:
            _download_lock.release()
        except RuntimeError:
            pass
    app.logger.warning("[Download] Lock manually reset via /download/reset (queue cleared: %s items)", queued_count)
    return jsonify({"ok": True, "was_held": held, "queue_cleared": queued_count})


@app.route("/download/log")
def download_log():
    """Return the last 100 lines of journal_club.log as plain text."""
    log_path = os.path.join(os.path.dirname(__file__), "journal_club.log")
    if not os.path.exists(log_path):
        return "No log file found.", 200, {"Content-Type": "text/plain"}
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    tail = "".join(lines[-100:])
    return tail, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/jcdebug")
def debug_page():
    """Simple debug dashboard: lock state + live log tail."""
    import time as _time
    acquired_at = _download_lock_meta["acquired_at"]
    held_secs = round(_time.time() - acquired_at, 1) if acquired_at else None
    lock_state = {
        "locked": acquired_at is not None,
        "held_seconds": held_secs,
        "session": _download_lock_meta["session"],
    }
    log_path = os.path.join(os.path.dirname(__file__), "journal_club.log")
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        log_tail = "".join(lines[-60:])
    else:
        log_tail = "(no log file yet)"

    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Journal Club Debug</title>
<meta http-equiv="refresh" content="5">
<style>
  body{{font-family:monospace;padding:20px;background:#0f1214;color:#e2e4e6}}
  h2{{color:#4db8d4}}
  .card{{background:#1e2124;padding:16px;border-radius:6px;margin-bottom:16px}}
  .locked{{color:#f87171}} .free{{color:#4ade80}}
  pre{{white-space:pre-wrap;word-break:break-all;font-size:12px;max-height:500px;overflow:auto}}
  button{{padding:8px 16px;background:#9f4200;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:14px}}
  button:hover{{background:#c45200}}
</style></head><body>
<h2>Journal Club — Debug Dashboard</h2>
<p style="color:#7a8490;font-size:12px">Auto-refreshes every 5 seconds</p>

<div class="card">
  <b>Download Lock</b><br><br>
  Status: <span class="{'locked' if lock_state['locked'] else 'free'}">
    {'🔒 LOCKED' if lock_state['locked'] else '🔓 FREE'}
  </span><br>
  {'Held for: <b>' + str(held_secs) + 's</b>' if held_secs is not None else ''}
  <br><br>
  <form method="POST" action="./download/reset">
    <button type="submit">Force Reset Lock</button>
  </form>
</div>

<div class="card">
  <b>Last 60 log lines</b> &nbsp;<a href="./download/log" style="color:#4db8d4;font-size:12px" target="_blank">view full log</a>
  <pre>{log_tail.replace('<','&lt;').replace('>','&gt;')}</pre>
</div>
</body></html>"""
    return html


@app.route("/bookmark/<int:article_id>", methods=["POST"])
def bookmark(article_id: int):
    new_state = storage.toggle_bookmark(article_id)
    return jsonify({"bookmarked": new_state})


# ── Journals routes ───────────────────────────────────────────────────────────

@app.route("/journals")
def journals():
    followed = storage.get_journals()
    followed_urls = {j["toc_url"] for j in followed}
    catalog = [
        {"name": e.name, "publisher": e.publisher, "toc_url": e.toc_url, "issn": e.issn}
        for e in CATALOG
        if e.toc_url not in followed_urls
    ]
    selected_id = request.args.get("selected", type=int)
    if selected_id is None and followed:
        selected_id = followed[0]["id"]
    toc_articles = storage.get_toc_articles(selected_id) if selected_id else []
    reading_list_ids = storage.get_reading_list_ids()
    reading_list_sent_dates = storage.get_reading_list_sent_dates()
    downloaded_article_map = storage.get_downloaded_toc_article_map(selected_id) if selected_id else {}
    selected_journal = next((j for j in followed if j["id"] == selected_id), None)
    return render_template(
        "journals.html",
        page="journals",
        followed=followed,
        catalog=catalog,
        selected_id=selected_id,
        selected_journal=selected_journal,
        toc_articles=toc_articles,
        reading_list_ids=reading_list_ids,
        reading_list_sent_dates=reading_list_sent_dates,
        downloaded_article_map=downloaded_article_map,
    )


@app.route("/journals/add", methods=["POST"])
def journals_add():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    publisher = data.get("publisher", "generic").strip()
    toc_url = data.get("toc_url", "").strip()
    issn = data.get("issn") or None

    if not name or not toc_url:
        return jsonify({"error": "name and toc_url are required"}), 400

    journal_id = storage.add_journal(name, publisher, toc_url, issn)
    j = storage.get_journal(journal_id)
    threading.Thread(target=_refresh_journal, args=(j,), daemon=True).start()
    return jsonify({"journal_id": journal_id, "name": name})


@app.route("/journals/<int:journal_id>/status")
def journals_status(journal_id: int):
    j = storage.get_journal(journal_id)
    if j is None:
        return jsonify({"error": "not found"}), 404
    articles = storage.get_toc_articles(journal_id)
    return jsonify({
        "last_checked": j.get("last_checked"),
        "article_count": len(articles),
        "current_issue_label": j.get("current_issue_label", ""),
    })


@app.route("/journals/<int:journal_id>/refresh", methods=["POST"])
def journals_refresh(journal_id: int):
    j = storage.get_journal(journal_id)
    if j is None:
        return jsonify({"error": "Journal not found"}), 404
    threading.Thread(target=_refresh_journal, args=(j,), daemon=True).start()
    return jsonify({"status": "refreshing"})


@app.route("/journals/<int:journal_id>/settings", methods=["POST"])
def journals_settings(journal_id: int):
    data = request.get_json(silent=True) or {}
    n = data.get("issues_to_fetch")
    if not isinstance(n, int) or not (1 <= n <= 52):
        return jsonify({"error": "issues_to_fetch must be an integer between 1 and 52"}), 400
    if storage.get_journal(journal_id) is None:
        return jsonify({"error": "Journal not found"}), 404
    storage.set_journal_issue_span(journal_id, n)
    return jsonify({"status": "saved"})


@app.route("/journals/<int:journal_id>", methods=["DELETE"])
def journals_delete(journal_id: int):
    storage.remove_journal(journal_id)
    return jsonify({"status": "removed"})


@app.route("/journals/<int:journal_id>/toc")
def journals_toc(journal_id: int):
    articles = storage.get_toc_articles(journal_id)
    reading_list_ids = storage.get_reading_list_ids()
    for a in articles:
        a["in_reading_list"] = a["id"] in reading_list_ids
    return jsonify(articles)


# ── Reading List routes ───────────────────────────────────────────────────────

@app.route("/reading-list")
def reading_list_page():
    items = storage.get_reading_list()
    return jsonify(items)


@app.route("/reading-list/add", methods=["POST"])
def reading_list_add():
    data = request.get_json(force=True) or {}
    toc_article_id = data.get("toc_article_id")
    if not toc_article_id:
        return jsonify({"error": "toc_article_id required"}), 400
    storage.add_to_reading_list(toc_article_id)
    return jsonify({"status": "added"})


@app.route("/reading-list/remove", methods=["POST"])
def reading_list_remove():
    data = request.get_json(force=True) or {}
    toc_article_id = data.get("toc_article_id")
    if not toc_article_id:
        return jsonify({"error": "toc_article_id required"}), 400
    storage.remove_from_reading_list(toc_article_id)
    return jsonify({"status": "removed"})


@app.route("/reading-list/email", methods=["POST"])
def reading_list_email():
    with _email_job_lock:
        if _email_job["running"]:
            return jsonify({"error": "Email job already running"}), 409
    rc = get_runtime_config()
    if not rc.resend_api_key or not rc.resend_from:
        return jsonify({"error": "Email not configured — go to Settings"}), 400
    to_addrs = [a for a in [rc.email_to_1, rc.email_to_2, rc.email_to_3] if a]
    if not to_addrs:
        return jsonify({"error": "No recipient addresses configured — go to Settings"}), 400
    items = storage.get_reading_list()
    if not items:
        return jsonify({"error": "Reading list is empty"}), 400

    with _email_job_lock:
        _email_job.update({
            "running": True, "status": "downloading",
            "current": 0,
            "total": len([it for it in items if not it.get("pdf_path")]),
            "error": None, "attached": 0, "failed_count": 0,
        })

    threading.Thread(target=_run_email_job, args=(items, rc), daemon=True).start()
    return jsonify({"status": "started", "total": len(items)})


@app.route("/reading-list/email/status")
def reading_list_email_status():
    return jsonify(dict(_email_job))


# ── Settings routes ──────────────────────────────────────────────────────────

@app.route("/settings")
def settings():
    s = storage.get_all_settings()
    rc = get_runtime_config()
    return render_template("settings.html", page="settings", s=s, cfg=rc)


@app.route("/settings", methods=["POST"])
def settings_save():
    data = request.get_json(force=True) or {}
    for key in storage._SETTINGS_KEYS:
        if key in data:
            storage.set_setting(key, data[key])
    return jsonify({"status": "saved"})


# ── Admin routes ─────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == cfg.admin_password:
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_settings"))
        error = "Incorrect password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("settings"))


@app.route("/admin/settings", methods=["GET"])
@require_admin
def admin_settings():
    s = storage.get_all_settings()
    rc = get_runtime_config()
    return render_template("admin_settings.html", page="admin", cfg=rc)


@app.route("/admin/settings", methods=["POST"])
@require_admin
def admin_settings_save():
    data = request.get_json(force=True) or {}
    for key in ["huji_email", "huji_password", "resend_api_key", "resend_from"]:
        if key in data:
            storage.set_setting(key, data[key])
    return jsonify({"status": "saved"})


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5001, use_reloader=False)
