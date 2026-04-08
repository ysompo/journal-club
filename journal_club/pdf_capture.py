# journal_club/pdf_capture.py
import os
import time
from playwright.sync_api import BrowserContext, Page

_SKIP_EXTS = ('.ttf', '.woff', '.otf', '.eot', '.svg', '.css',
              '.js', '.png', '.jpg', '.gif', '.ico')

def _looks_like_pdf_response(url: str, content_type: str) -> bool:
    if any(url.endswith(ext) for ext in _SKIP_EXTS):
        return False
    ct = content_type.lower()
    return ("pdf" in ct or "octet-stream" in ct or url.lower().endswith('.pdf')
            or "chrome-extension" in url)

def attach_pdf_hooks(context: BrowserContext, page: Page) -> list:
    """
    Registers response + download hooks on context and page.
    Returns a shared list; first element will be the captured PDF bytes when found.
    """
    captured: list[bytes] = []

    def on_response(response):
        if captured:
            return
        url = response.url
        ct = response.headers.get("content-type", "")
        if not _looks_like_pdf_response(url, ct):
            return
        if response.status != 200:
            return
        try:
            body = response.body()
            if body[:4] == b'%PDF':
                print(f"   [PDF captured] {len(body):,} bytes from {url[:80]}")
                captured.append(body)
        except Exception as e:
            print(f"   [PDF body error] {e}")

    def on_download(download):
        if captured:
            return
        tmp = os.path.join(os.environ.get("TEMP", "C:\\Temp"), download.suggested_filename)
        download.save_as(tmp)
        with open(tmp, "rb") as f:
            body = f.read()
        if body[:4] == b'%PDF':
            print(f"   [PDF via download] {len(body):,} bytes — {download.suggested_filename}")
            captured.append(body)

    def on_new_page(new_page):
        new_page.on("response", on_response)
        new_page.on("download", on_download)

    context.on("page", on_new_page)
    page.on("response", on_response)
    page.on("download", on_download)

    return captured


def save_pdf(captured: list[bytes], out_path: str) -> bool:
    """Write first captured PDF to out_path. Returns True on success."""
    if not captured:
        return False
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(captured[0])
    print(f"   Saved -> {out_path} ({os.path.getsize(out_path):,} bytes)")
    return True


def wait_for_pdf(captured: list, timeout_s: int = 30) -> bool:
    """Poll until PDF is captured or timeout. Returns True if captured."""
    for remaining in range(timeout_s, 0, -5):
        if captured:
            return True
        print(f"   ... waiting {remaining}s")
        time.sleep(5)
    return bool(captured)
