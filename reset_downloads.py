#!/usr/bin/env python3
"""
Reset Journal Club download database.
Clears pdf_path to mark all articles as "not downloaded".

Usage:
    python reset_downloads.py --articles   # Clear all pdf_path (reset all downloads)
    python reset_downloads.py --all        # Full reset (delete all articles & history)
"""
import sys
import sqlite3
from pathlib import Path
from journal_club.storage import _DB_PATH

# Handle Unicode on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def reset_pdf_paths():
    """Clear all pdf_path values, marking articles as not downloaded."""
    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()

    # Check current state
    result = cursor.execute("SELECT COUNT(*) FROM articles WHERE pdf_path IS NOT NULL").fetchone()
    count = result[0] if result else 0

    if count == 0:
        print("✓ No downloads to reset (all articles already marked as not downloaded)")
        conn.close()
        return

    print(f"⚠ Found {count} downloaded articles")
    confirm = input(f"Clear pdf_path for {count} articles? (type 'yes' to confirm): ")

    if confirm.lower() != 'yes':
        print("Cancelled")
        conn.close()
        return

    # Reset
    cursor.execute("UPDATE articles SET pdf_path = NULL, downloaded_at = NULL")
    conn.commit()

    result = cursor.execute("SELECT COUNT(*) FROM articles WHERE pdf_path IS NOT NULL").fetchone()
    remaining = result[0] if result else 0

    print(f"✓ Reset complete. Remaining downloads: {remaining}")
    conn.close()


def reset_all():
    """Delete all articles and reading list history."""
    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()

    # Check counts
    articles = cursor.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    reading_list = cursor.execute("SELECT COUNT(*) FROM reading_list").fetchone()[0]

    print(f"⚠ This will delete:")
    print(f"  - {articles} articles")
    print(f"  - {reading_list} reading list entries")
    print(f"  - All download history")

    confirm = input("Type 'DELETE ALL' to confirm full reset: ")

    if confirm != 'DELETE ALL':
        print("Cancelled")
        conn.close()
        return

    # Delete
    cursor.execute("DELETE FROM reading_list")
    cursor.execute("DELETE FROM articles")
    conn.commit()

    print("✓ Full reset complete. Database is now empty.")
    print("  Journal list and TOC articles are preserved.")
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python reset_downloads.py --articles   # Clear all pdf_path (mark as not downloaded)")
        print("  python reset_downloads.py --all        # Full reset (delete all articles & history)")
        sys.exit(1)

    if sys.argv[1] == "--articles":
        reset_pdf_paths()
    elif sys.argv[1] == "--all":
        reset_all()
    else:
        print(f"Unknown option: {sys.argv[1]}")
        sys.exit(1)
