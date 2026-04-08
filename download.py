#!/usr/bin/env python3
"""
Journal Club PDF Downloader
Usage: python download.py <article_url>
"""
import sys
import os
import time
import re

from journal_club.config import load_config
from journal_club.browser import launch_browser
from journal_club.pdf_capture import attach_pdf_hooks, save_pdf, wait_for_pdf
from journal_club.auth_oa_check import check_open_access
from journal_club.router import detect_publisher, Publisher

from journal_club.auth_jama import authenticate_jama
from journal_club.auth_ovid import authenticate_ovid
from journal_club.auth_elsevier import authenticate_elsevier
from journal_club.auth_openathens import authenticate_openathens
from journal_club.auth_springer import authenticate_springer


def slugify(url: str) -> str:
    """Turn a URL into a safe filename."""
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', url.split("//")[-1])
    return slug[:80]


def main():
    if len(sys.argv) < 2:
        print("Usage: python download.py <article_url>")
        sys.exit(1)

    article_url = sys.argv[1]
    cfg = load_config("config.yaml")

    os.makedirs(cfg.output_dir, exist_ok=True)
    out_path = os.path.join(cfg.output_dir, slugify(article_url) + ".pdf")

    publisher = detect_publisher(article_url)
    print(f"\nArticle: {article_url}")
    print(f"Publisher: {publisher.name}")
    print(f"Output: {out_path}")
    print("=" * 60)

    with launch_browser(cfg.chrome_profile, cfg.chrome_path) as (_, browser, context, page):
        captured = attach_pdf_hooks(context, page)

        # Step 1: Navigate to article + try open access
        page.goto(article_url, wait_until="domcontentloaded")
        time.sleep(3)

        oa_ok, pdf_url = check_open_access(page, context, captured, timeout_s=20)

        if oa_ok:
            pass  # OA — PDF already captured
        else:
            # Step 2: Publisher-specific auth
            auth_kwargs = dict(
                page=page,
                article_url=article_url,
                email=cfg.huji_email,
                password=cfg.huji_password,
                captured=captured,
            )
            if publisher == Publisher.JAMA:
                authenticate_jama(**auth_kwargs)
            elif publisher == Publisher.OVID:
                authenticate_ovid(**auth_kwargs)
            elif publisher == Publisher.ELSEVIER:
                authenticate_elsevier(**auth_kwargs)
            elif publisher == Publisher.SPRINGER_NATURE:
                authenticate_springer(**auth_kwargs)
            else:  # OPENATHENS_GENERIC
                authenticate_openathens(**auth_kwargs)

            wait_for_pdf(captured, timeout_s=60)

            # Fallback: if PDF URL was found in OA check, navigate directly to it
            if not captured and pdf_url:
                print(f"\n[Fallback] Navigating directly to PDF URL after auth...")
                print(f"   {pdf_url[:80]}")
                try:
                    pdf_tab = context.new_page()
                    pdf_tab.goto(pdf_url, wait_until="commit", timeout=20_000)
                    wait_for_pdf(captured, timeout_s=30)
                except Exception as e:
                    print(f"   Fallback error: {e}")

        print("\n" + "=" * 60)
        if save_pdf(captured, out_path):
            size = os.path.getsize(out_path)
            if size < 10_000:
                print(f"WARNING: file is only {size} bytes — may not be a full PDF")
            else:
                print(f"SUCCESS: {out_path} ({size:,} bytes)")
        else:
            print("FAILED: PDF not captured — see output above")
            sys.exit(1)

        try:
            input("\nPress Enter to close Chrome...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
