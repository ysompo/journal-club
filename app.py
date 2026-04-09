#!/usr/bin/env python3
"""
Journal Club — Flask web app
Usage: python app.py
Then open http://localhost:5000
"""
from __future__ import annotations

import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for

from journal_club.config import load_config
from journal_club.resolver import resolve
import journal_club.storage as storage

app = Flask(__name__)
cfg = load_config("config.yaml")


# ── Routes ────────────────────────────────────────────────────────────────────

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
    # If called via AJAX (polling for download status) return JSON
    if request.headers.get("Accept") == "application/json":
        return jsonify(a)
    return render_template("article.html", article=a, page="history")


@app.route("/download", methods=["POST"])
def download():
    """
    Accept JSON {input: "<pmid | doi | url>"}.
    Resolves metadata immediately, saves a pending DB record, then triggers
    the browser-based PDF download in a background thread.
    Returns JSON {article_id, title, url}.
    """
    data = request.get_json(force=True)
    input_str = (data or {}).get("input", "").strip()
    if not input_str:
        return jsonify({"error": "No input provided"}), 400

    # Resolve metadata without a browser (fast)
    try:
        meta = resolve(input_str)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Save a pending record immediately so the UI can show progress
    article_id = storage.save_article(meta, pdf_path=None)

    # Run the browser download in a background thread
    def _run():
        try:
            from download import download_article
            _, pdf_path = download_article(meta.url, cfg)
            storage.update_pdf_path(article_id, pdf_path)
        except Exception as e:
            print(f"[Download thread] Error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return jsonify({
        "article_id": article_id,
        "title": meta.title or meta.url,
        "url": meta.url,
    })


@app.route("/bookmark/<int:article_id>", methods=["POST"])
def bookmark(article_id: int):
    new_state = storage.toggle_bookmark(article_id)
    return jsonify({"bookmarked": new_state})


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
