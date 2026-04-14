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
import journal_club.storage as storage

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)   # ephemeral — sessions reset on restart (fine for local use)

# Support deployment behind a reverse proxy at /tools/journal-club
import os
script_name = os.environ.get("SCRIPT_NAME", "")
if script_name:
    app.config["APPLICATION_ROOT"] = script_name

cfg = load_config("config.yaml")

if not app.debug:
    _log_handler = RotatingFileHandler("journal_club.log", maxBytes=1_000_000, backupCount=3)
    _log_handler.setLevel(logging.WARNING)
    _log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    app.logger.addHandler(_log_handler)
    app.logger.setLevel(logging.WARNING)


def require_admin(f):
    """Decorator: redirect to /admin/login if not authenticated as admin."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def require_journal_auth(f):
    """Decorator: redirect to /login if not authenticated as journal user."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("journal_authenticated"):
            return redirect(url_for("login", next=request.path))
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


# ── Login/Auth routes ─────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login/Signup page."""
    error = None
    signup_done = False
    tab = "login"

    if request.method == "POST":
        tab = request.form.get("tab", "login")

        if tab == "login":
            access_password = request.form.get("access_password", "").strip()
            if access_password == cfg.journal_access_password:
                session["journal_authenticated"] = True
                return redirect(request.args.get("next") or url_for("journals"))
            error = "Incorrect access password."

        elif tab == "signup":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            if not name or not email:
                error = "Name and email are required."
            else:
                try:
                    storage.add_access_request(name, email)
                    signup_done = True
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        error = "This email has already been registered."
                    else:
                        error = "An error occurred. Please try again."

    return render_template(
        "login.html",
        error=error,
        signup_done=signup_done,
        tab=tab,
    )


@app.route("/logout", methods=["POST"])
def logout():
    """Logout and redirect to login page."""
    session.pop("journal_authenticated", None)
    return redirect(url_for("login"))


# ── Existing routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("journals"))


@app.route("/add")
@require_journal_auth
def add():
    return render_template("add_article.html", page="add")


@app.route("/history")
@require_journal_auth
def history():
    articles = storage.get_history()
    return render_template("history.html", articles=articles, page="history")


@app.route("/bookmarks")
@require_journal_auth
def bookmarks():
    articles = storage.get_bookmarks()
    return render_template("bookmarks.html", articles=articles, page="bookmarks")


@app.route("/article/<int:article_id>")
@require_journal_auth
def article(article_id: int):
    a = storage.get_by_id(article_id)
    if a is None:
        return "Article not found", 404
    if request.headers.get("Accept") == "application/json":
        return jsonify(a)
    return render_template("article.html", article=a, page="history")


@app.route("/pdf/<int:article_id>")
@require_journal_auth
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
@require_journal_auth
def download():
    """
    Accept JSON {input: "<pmid | doi | url>", toc_article_id: <int|null>}.
    Resolves metadata immediately, saves a pending DB record, then triggers
    the browser-based PDF download in a background thread.
    Returns JSON {article_id, title, url}.
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

    if not _download_lock.acquire(blocking=False):
        return jsonify({"error": "A download is already in progress — please wait for it to finish."}), 409

    try:
        article_id = storage.save_article(meta, pdf_path=None)
        runtime_cfg = get_runtime_config()
    except Exception as e:
        _download_lock.release()
        app.logger.error("Download setup failed: %s", e, exc_info=True)
        return jsonify({"error": f"Server error while preparing download: {e}"}), 500

    def _run():
        try:
            storage.set_download_error(article_id, "")  # clear any prior error on retry
            if not runtime_cfg.huji_email or not runtime_cfg.huji_password:
                raise ValueError(
                    "HUJI credentials not configured — go to Settings to enter your email and password."
                )
            from download import download_article
            _, pdf_path = download_article(meta.url, runtime_cfg)
            storage.update_pdf_path(article_id, pdf_path)
            if toc_article_id:
                storage.link_reading_list_to_article(toc_article_id, article_id)
        except Exception as e:
            app.logger.error("[Download thread] article_id=%s error: %s", article_id, e, exc_info=True)
            storage.set_download_error(article_id, str(e))
        finally:
            _download_lock.release()

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({
        "article_id": article_id,
        "title": meta.title or meta.url,
        "url": meta.url,
    })


@app.route("/download/status/<int:article_id>")
@require_journal_auth
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


@app.route("/bookmark/<int:article_id>", methods=["POST"])
@require_journal_auth
def bookmark(article_id: int):
    new_state = storage.toggle_bookmark(article_id)
    return jsonify({"bookmarked": new_state})


# ── Journals routes ───────────────────────────────────────────────────────────

@app.route("/journals")
@require_journal_auth
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
@require_journal_auth
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
@require_journal_auth
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
@require_journal_auth
def journals_refresh(journal_id: int):
    j = storage.get_journal(journal_id)
    if j is None:
        return jsonify({"error": "Journal not found"}), 404
    threading.Thread(target=_refresh_journal, args=(j,), daemon=True).start()
    return jsonify({"status": "refreshing"})


@app.route("/journals/<int:journal_id>/settings", methods=["POST"])
@require_journal_auth
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
@require_journal_auth
def journals_delete(journal_id: int):
    storage.remove_journal(journal_id)
    return jsonify({"status": "removed"})


@app.route("/journals/<int:journal_id>/toc")
@require_journal_auth
def journals_toc(journal_id: int):
    articles = storage.get_toc_articles(journal_id)
    reading_list_ids = storage.get_reading_list_ids()
    for a in articles:
        a["in_reading_list"] = a["id"] in reading_list_ids
    return jsonify(articles)


# ── Reading List routes ───────────────────────────────────────────────────────

@app.route("/reading-list")
@require_journal_auth
def reading_list_page():
    items = storage.get_reading_list()
    return jsonify(items)


@app.route("/reading-list/add", methods=["POST"])
@require_journal_auth
def reading_list_add():
    data = request.get_json(force=True) or {}
    toc_article_id = data.get("toc_article_id")
    if not toc_article_id:
        return jsonify({"error": "toc_article_id required"}), 400
    storage.add_to_reading_list(toc_article_id)
    return jsonify({"status": "added"})


@app.route("/reading-list/remove", methods=["POST"])
@require_journal_auth
def reading_list_remove():
    data = request.get_json(force=True) or {}
    toc_article_id = data.get("toc_article_id")
    if not toc_article_id:
        return jsonify({"error": "toc_article_id required"}), 400
    storage.remove_from_reading_list(toc_article_id)
    return jsonify({"status": "removed"})


@app.route("/reading-list/email", methods=["POST"])
@require_journal_auth
def reading_list_email():
    rc = get_runtime_config()
    if not rc.resend_api_key or not rc.resend_from:
        return jsonify({"error": "Email not configured — go to Settings"}), 400
    to_addrs = [a for a in [rc.email_to_1, rc.email_to_2, rc.email_to_3] if a]
    if not to_addrs:
        return jsonify({"error": "No recipient addresses configured — go to Settings"}), 400
    items = storage.get_reading_list()
    if not items:
        return jsonify({"error": "Reading list is empty"}), 400
    try:
        attached = send_reading_list(
            articles=items,
            api_key=rc.resend_api_key,
            from_addr=rc.resend_from,
            to_addrs=to_addrs,
        )
        storage.mark_reading_list_sent()
        return jsonify({"status": "sent", "articles": len(items), "pdfs_attached": attached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Settings routes ──────────────────────────────────────────────────────────

@app.route("/settings")
@require_journal_auth
def settings():
    s = storage.get_all_settings()
    rc = get_runtime_config()
    return render_template("settings.html", page="settings", s=s, cfg=rc)


@app.route("/settings", methods=["POST"])
@require_journal_auth
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
    for key in ["resend_api_key", "resend_from"]:
        if key in data:
            storage.set_setting(key, data[key])
    return jsonify({"status": "saved"})


@app.route("/admin/access-requests", methods=["GET"])
@require_admin
def admin_access_requests():
    """Admin page for approving/denying signup requests."""
    pending = storage.get_access_requests(status="pending")
    approved = storage.get_access_requests(status="approved")
    denied = storage.get_access_requests(status="denied")
    return render_template(
        "admin_access_requests.html",
        pending=pending,
        approved=approved,
        denied=denied,
        page="admin",
    )


@app.route("/admin/access-requests/<int:request_id>/approve", methods=["POST"])
@require_admin
def admin_approve_request(request_id: int):
    """Approve an access request and send email with access password."""
    requests = storage.get_access_requests()
    req = next((r for r in requests if r["id"] == request_id), None)
    if not req:
        return jsonify({"error": "Request not found"}), 404

    storage.approve_access_request(request_id)

    # Send approval email with access password if Resend is configured
    rc = get_runtime_config()
    if rc.resend_api_key and rc.resend_from and req["email"]:
        try:
            from resend import Resend
            client = Resend(api_key=rc.resend_api_key)
            client.emails.send({
                "from": rc.resend_from,
                "to": req["email"],
                "subject": "Your Journal Club Access Approved",
                "html": f"""
                <h2>Welcome to Journal Club!</h2>
                <p>Your access request has been approved.</p>
                <p>You can now log in using this access password:</p>
                <p style="font-size: 18px; font-weight: bold; font-family: monospace; background: #f0f0f0; padding: 10px; border-radius: 4px;">
                    {rc.journal_access_password}
                </p>
                <p><a href="https://labor-ai.org/tools/journal-club">Visit Journal Club</a></p>
                <p>Keep this password safe and do not share it.</p>
                """,
            })
        except Exception as e:
            print(f"[Email] Failed to send approval email: {e}")

    return jsonify({"status": "approved"})


@app.route("/admin/access-requests/<int:request_id>/deny", methods=["POST"])
@require_admin
def admin_deny_request(request_id: int):
    """Deny an access request."""
    storage.deny_access_request(request_id)
    return jsonify({"status": "denied"})


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
