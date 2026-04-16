#!/usr/bin/env python3
"""
Journal Club PDF Downloader
Usage:
    python download.py <article_url>
    python download.py <pmid>
    python download.py https://pubmed.ncbi.nlm.nih.gov/<pmid>/
    python download.py 10.1056/NEJMoa2504068   (DOI)
"""
import sys
import os
import time
import re
import json as _json

from journal_club.config import load_config, Config
from journal_club.browser import launch_browser, set_download_behavior
from journal_club.pdf_capture import attach_pdf_hooks, save_pdf, wait_for_pdf
from journal_club.auth_oa_check import check_open_access
from journal_club.router import detect_publisher, Publisher
from journal_club.resolver import resolve, ArticleMetadata
import journal_club.storage as storage

from journal_club.auth_jama import authenticate_jama
from journal_club.auth_ovid import authenticate_ovid
from journal_club.auth_elsevier import authenticate_elsevier
from journal_club.auth_openathens import authenticate_openathens
from journal_club.auth_springer import authenticate_springer


_COOKIE_FILE = ".jc_session_cookies.json"


def _load_cookies(context, cfg) -> None:
    """Load saved session cookies from disk into the Playwright context."""
    cookie_path = os.path.join(cfg.output_dir, _COOKIE_FILE)
    if not os.path.exists(cookie_path):
        return
    try:
        with open(cookie_path, "r", encoding="utf-8") as f:
            cookies = _json.load(f)
        context.add_cookies(cookies)
        print(f"[Cookies] Loaded {len(cookies)} session cookies")
    except Exception as e:
        print(f"[Cookies] Could not load cookies: {e}")


def _save_cookies(context, cfg) -> None:
    """Save all current Playwright context cookies to disk."""
    try:
        cookies = context.cookies()
        cookie_path = os.path.join(cfg.output_dir, _COOKIE_FILE)
        with open(cookie_path, "w", encoding="utf-8") as f:
            _json.dump(cookies, f)
        print(f"[Cookies] Saved {len(cookies)} session cookies")
    except Exception as e:
        print(f"[Cookies] Could not save cookies: {e}")


def slugify(url: str) -> str:
    """Turn a URL into a safe filename (max 80 chars)."""
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', url.split("//")[-1])
    return slug[:80]


def download_article(input_str: str, cfg: Config) -> tuple[ArticleMetadata, str]:
    """
    Resolve *input_str* (PMID / PubMed URL / DOI / article URL), authenticate,
    download the PDF, save it to disk, and return (metadata, pdf_path).

    Raises RuntimeError if the PDF could not be captured.
    """
    # ── 1. Resolve input → ArticleMetadata + publisher URL ───────────────────
    meta = resolve(input_str)
    article_url = meta.url

    os.makedirs(cfg.output_dir, exist_ok=True)
    out_path = os.path.join(cfg.output_dir, slugify(article_url) + ".pdf")

    publisher = detect_publisher(article_url)
    print(f"\nArticle: {article_url}")
    if meta.title:
        print(f"Title:   {meta.title[:80]}")
    print(f"Publisher: {publisher.name}")
    print(f"Output: {out_path}")
    print("=" * 60)

    # ── 1b. Try Unpaywall for open-access PDF ──────────────────────────────
    if meta.doi:
        from journal_club.unpaywall import query_unpaywall
        oa = query_unpaywall(meta.doi, cfg.huji_email)
        if oa and oa.get("pdf_url"):
            from journal_club.http_download import download_pdf_http
            print(f"[Unpaywall] Found OA PDF: {oa['pdf_url'][:80]}")
            if download_pdf_http(oa["pdf_url"], out_path):
                size = os.path.getsize(out_path)
                print(f"SUCCESS (Unpaywall): {out_path} ({size:,} bytes)")
                return meta, out_path
            print("[Unpaywall] HTTP download failed, falling through to browser...")

    captured = []

    # ── 2. Browser session (up to 2 attempts) ────────────────────────────────
    for attempt in range(1, 3):
        if attempt > 1:
            print(f"\n[Retry] Attempt {attempt} — PDF not captured, retrying browser session...")
            time.sleep(3)
            captured = []

        with launch_browser(cfg.chrome_profile, cfg.chrome_path) as (_, browser, context, page):
            captured = attach_pdf_hooks(context, page)
            set_download_behavior(context, page, cfg.output_dir)
            _load_cookies(context, cfg)

            # For ScienceDirect: visit the homepage first so Cloudflare can run its
            # invisible JavaScript challenge and issue a cf_clearance cookie.
            # Direct article navigation on a fresh profile is blocked before any
            # cookies are set.
            if publisher == Publisher.ELSEVIER or "sciencedirect.com" in article_url:
                print("[Elsevier] Warming up Cloudflare session via homepage...")
                try:
                    page.goto("https://www.sciencedirect.com",
                              wait_until="domcontentloaded", timeout=20_000)
                    time.sleep(3)  # let Cloudflare JS challenge complete
                    print(f"   Homepage loaded: {page.title()[:60]}")
                except Exception as _e:
                    print(f"   Homepage warm-up error (continuing): {_e}")

            page.goto(article_url, wait_until="domcontentloaded")
            time.sleep(3)

            oa_ok, pdf_url = check_open_access(page, context, captured, timeout_s=20)

            if not oa_ok:
                auth_kwargs = dict(
                    page=page,
                    article_url=article_url,
                    email=cfg.huji_email,
                    password=cfg.huji_password,
                    captured=captured,
                    output_dir=cfg.output_dir,
                )
                auth_pdf_url = None
                if publisher == Publisher.JAMA:
                    authenticate_jama(**auth_kwargs)
                elif publisher == Publisher.OVID:
                    authenticate_ovid(**auth_kwargs)
                elif publisher == Publisher.ELSEVIER:
                    authenticate_elsevier(**auth_kwargs)
                elif publisher == Publisher.SPRINGER_NATURE:
                    authenticate_springer(**auth_kwargs)
                else:  # OPENATHENS_GENERIC
                    auth_pdf_url = authenticate_openathens(**auth_kwargs)

                wait_for_pdf(captured, timeout_s=15, output_dir=cfg.output_dir)

                fallback_url = pdf_url or auth_pdf_url
                if not captured and fallback_url:
                    pdf_url = fallback_url
                if not captured and pdf_url:
                    print(f"\n[Fallback] Navigating directly to PDF URL after auth...")
                    print(f"   {pdf_url[:80]}")
                    try:
                        pdf_tab = context.new_page()
                        pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
                        wait_for_pdf(captured, timeout_s=45, output_dir=cfg.output_dir)
                    except Exception as e:
                        print(f"   Fallback error: {e}")

            time.sleep(5)  # grace period for in-flight PDF downloads

            if captured:
                _save_cookies(context, cfg)

        if captured:
            break

    # ── 3. Save PDF ───────────────────────────────────────────────────────────
    # Called AFTER browser closes so Chrome extension bytes fired during
    # shutdown are not missed.
    print("\n" + "=" * 60)
    if not save_pdf(captured, out_path):
        raise RuntimeError("PDF not captured — see output above")

    size = os.path.getsize(out_path)
    if size < 10_000:
        print(f"WARNING: file is only {size} bytes — may not be a full PDF")
    else:
        print(f"SUCCESS: {out_path} ({size:,} bytes)")

    return meta, out_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python download.py <article_url | pmid | doi | pubmed_url>")
        sys.exit(1)

    cfg = load_config("config.yaml")
    try:
        meta, pdf_path = download_article(sys.argv[1], cfg)
        storage.save_article(meta, pdf_path)
    except RuntimeError as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
