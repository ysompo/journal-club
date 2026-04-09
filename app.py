#!/usr/bin/env python3
"""
Journal Club — Flask web app
Usage: python app.py
Then open http://localhost:5000
"""
from __future__ import annotations

import threading

from flask import Flask, render_template, request, jsonify, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

from journal_club.config import Config, load_config
from journal_club.resolver import resolve
from journal_club.journals_catalog import CATALOG
from journal_club.toc_scraper import scrape
from journal_club.mailer import send_reading_list
import journal_club.storage as storage

app = Flask(__name__)
cfg = load_config("config.yaml")


def get_runtime_config() -> Config:
    """Return Config with DB settings overriding config.yaml values where set."""
    s = storage.get_all_settings()
    return Config(
        huji_email=s.get("huji_email") or cfg.huji_email,
        huji_password=s.get("huji_password") or cfg.huji_password,
        output_dir=cfg.output_dir,
        chrome_profile=cfg.chrome_profile,
        chrome_path=cfg.chrome_path,
        email_to=s.get("email_to") or cfg.email_to,
        smtp_host=s.get("smtp_host") or cfg.smtp_host,
        smtp_port=int(s.get("smtp_port") or cfg.smtp_port),
        smtp_user=s.get("smtp_user") or cfg.smtp_user,
        smtp_password=s.get("smtp_password") or cfg.smtp_password,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _refresh_journal(journal: dict) -> None:
    """Scrape TOC for a single journal and persist to DB. Safe to call in any thread."""
    try:
        publisher = next(
            (e.publisher for e in CATALOG if e.toc_url == journal["toc_url"]),
            "generic",
        )
        result = scrape(publisher, journal["toc_url"], issn=journal.get("issn"))
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


# ── Existing routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("add"))


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


@app.route("/download", methods=["POST"])
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

    article_id = storage.save_article(meta, pdf_path=None)

    runtime_cfg = get_runtime_config()

    def _run():
        try:
            from download import download_article
            _, pdf_path = download_article(meta.url, runtime_cfg)
            storage.update_pdf_path(article_id, pdf_path)
            if toc_article_id:
                storage.link_reading_list_to_article(toc_article_id, article_id)
        except Exception as e:
            print(f"[Download thread] Error: {e}")

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({
        "article_id": article_id,
        "title": meta.title or meta.url,
        "url": meta.url,
    })


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
    rc = get_runtime_config()
    if not rc.email_to or not rc.smtp_user or not rc.smtp_password:
        return jsonify({"error": "Email not configured — go to Settings"}), 400
    items = storage.get_reading_list()
    if not items:
        return jsonify({"error": "Reading list is empty"}), 400
    try:
        attached = send_reading_list(
            articles=items,
            to_addr=rc.email_to,
            smtp_host=rc.smtp_host,
            smtp_port=rc.smtp_port,
            smtp_user=rc.smtp_user,
            smtp_password=rc.smtp_password,
        )
        return jsonify({"status": "sent", "articles": len(items), "pdfs_attached": attached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
