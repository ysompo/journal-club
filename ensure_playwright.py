#!/usr/bin/env python3
"""
Ensure Playwright browsers are installed before starting the app.
Run this at app startup to fix missing Chromium on Render.
"""
import os
import subprocess
import sys

def ensure_playwright_browsers():
    """Check if Playwright browsers exist; install if missing."""
    cache_dir = os.path.expanduser("~/.cache/ms-playwright")
    chromium_dir = os.path.join(cache_dir, "chromium-1208/chrome-linux64")
    chrome_exe = os.path.join(chromium_dir, "chrome")

    if os.path.exists(chrome_exe):
        print(f"✓ Playwright Chromium found at {chrome_exe}")
        return True

    print(f"⚠ Playwright Chromium not found. Installing browsers...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install"],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            print("✓ Playwright browsers installed successfully")
            return True
        else:
            print(f"✗ Playwright install failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Error installing Playwright: {e}")
        return False

if __name__ == "__main__":
    success = ensure_playwright_browsers()
    sys.exit(0 if success else 1)
