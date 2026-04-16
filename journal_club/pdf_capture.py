# journal_club/pdf_capture.py
import os
import time
import logging
from playwright.sync_api import BrowserContext, Page

logger = logging.getLogger(__name__)

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
    Also sets up Playwright route interception for known PDF URL patterns so that
    Chrome's built-in PDF viewer cannot consume the response body before we read it
    (CDP's Network.getResponseBody fails once the viewer has processed the bytes).
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
                logger.info(f"[PDF captured] {len(body):,} bytes from {url[:80]}")
                captured.append(body)
            else:
                logger.debug(f"[PDF response not PDF] first bytes: {body[:40]!r} — {url[:60]}")
        except Exception as e:
            # Chrome's built-in PDF viewer consumes response bytes before CDP can
            # read them back; response.body() raises "No data found" in that case.
            # Fix: launch Chrome with --disable-pdf-extension so PDFs download.
            logger.warning(f"[PDF body() failed] {type(e).__name__}: {e} — {url[:60]}")

    def on_download(download):
        if captured:
            return
        logger.info(f"[Download event] {download.suggested_filename}")

        # IMPORTANT: download.path() is a blocking Playwright call that waits for
        # the download to complete.  If called from the asyncio event thread (which
        # is where Playwright fires all callbacks in sync API mode), it deadlocks:
        # download.path() blocks the asyncio thread waiting for download-progress
        # events that ALSO need the asyncio thread to process.
        #
        # Fix: run the entire capture logic in a daemon background thread so the
        # asyncio event loop stays free to receive download-progress events.
        import threading as _threading

        def _capture_in_thread(dl):
            # Primary: download.path() — blocks until download completes, but now
            # runs in a background thread so asyncio is not blocked.
            try:
                file_path = dl.path()
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        body = f.read()
                    if body[:4] == b'%PDF':
                        if not captured:
                            logger.info(f"[PDF via download.path()] {len(body):,} bytes — {dl.suggested_filename}")
                            captured.append(body)
                        return
                    else:
                        logger.warning(f"[Download not PDF] first bytes: {body[:40]!r} — {dl.suggested_filename}")
            except Exception as e:
                logger.debug(f"[PDF download.path() error] {e}")

            # Fallback: save_as to temp dir.
            tmp = os.path.join(os.environ.get("TEMP", "C:\\Temp"), dl.suggested_filename or "download.pdf")
            try:
                dl.save_as(tmp)
            except Exception as e:
                logger.error(f"[PDF download save error] {e}")
                return
            try:
                with open(tmp, "rb") as f:
                    body = f.read()
                if body[:4] == b'%PDF':
                    if not captured:
                        logger.info(f"[PDF via download.save_as()] {len(body):,} bytes — {dl.suggested_filename}")
                        captured.append(body)
                else:
                    logger.warning(f"[Download saved not PDF] first bytes: {body[:40]!r}")
            except Exception as e:
                logger.error(f"[PDF download read error] {e}")

        _threading.Thread(target=_capture_in_thread, args=(download,), daemon=True).start()

    def on_new_page(new_page):
        new_page.on("response", on_response)
        new_page.on("download", on_download)

    context.on("page", on_new_page)
    page.on("response", on_response)
    page.on("download", on_download)

    # ── Route interception: read PDF bytes BEFORE Chrome's viewer consumes them ──
    # Chrome's built-in PDF viewer processes response bytes at the browser level,
    # making CDP Network.getResponseBody fail.  Route interception runs before
    # Chrome touches the response, so we always get the bytes.
    #
    # Elsevier CDN (pdf.sciencedirectassets.com) uses AWS-signed query-string auth
    # — no browser cookies needed — so route.fetch() works without cookie passing.
    def _route_pdf(route, request):
        if captured:
            try:
                route.continue_()
            except Exception:
                pass
            return
        try:
            resp = route.fetch(timeout=300_000)
            body = resp.body()
            ct = (resp.headers.get("content-type") or "").lower()
            if not captured and (body[:4] == b'%PDF' or "pdf" in ct):
                logger.info(f"[PDF route] Captured {len(body):,} bytes from {request.url[:70]}")
                captured.append(body)
            # Always fulfill so Chrome can render the page (may show viewer, irrelevant)
            route.fulfill(status=resp.status, headers=dict(resp.headers), body=body)
        except Exception as e:
            logger.debug(f"[PDF route] {type(e).__name__}: {e} — {request.url[:60]}")
            try:
                route.continue_()
            except Exception:
                pass

    # Only intercept the Elsevier S3 CDN (AWS-signed URLs, no Cloudflare).
    # Publisher-side endpoints (showPdf, pdfft, doi/pdf, pdfdirect, etc.) sit
    # behind Cloudflare — route.fetch() from Node.js causes Cloudflare to hang
    # the connection, blocking the asyncio event loop for 170+ seconds and
    # preventing on_download/on_response from firing at all.
    # Chrome handles those URLs natively (correct TLS fingerprint passes CF);
    # --disable-pdf-extension makes Chrome download PDFs instead of viewing them,
    # so the on_download hook captures the result without route interception.
    context.route("**/pdf.sciencedirectassets.com/**", _route_pdf)

    return captured


def save_pdf(captured: list[bytes], out_path: str) -> bool:
    """Write first captured PDF to out_path. Returns True on success."""
    if not captured:
        logger.error("[PDF save] No PDF was captured")
        return False
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(captured[0])
    size = os.path.getsize(out_path)
    logger.info(f"[PDF save] ✓ Saved {out_path} ({size:,} bytes)")
    return True


def wait_for_pdf(captured: list, timeout_s: int = 30, output_dir: str = None) -> bool:
    """Poll until PDF is captured or timeout. Returns True if captured.

    Also checks for recently-created PDF files in output_dir (fallback for CDP downloads).
    If a valid PDF is found, it's appended to captured list.
    """
    import glob as _glob
    start_time = time.time()

    while time.time() - start_time < timeout_s:
        if captured:
            logger.info(f"[PDF wait] ✓ PDF captured!")
            return True

        # Fallback: check output_dir for recently-created PDFs (CDP downloads)
        if output_dir:
            try:
                now = time.time()
                for pdf_path in _glob.glob(os.path.join(output_dir, "*.pdf")):
                    try:
                        mtime = os.path.getmtime(pdf_path)
                        size = os.path.getsize(pdf_path)
                        # If modified within last 30s and > 10KB, it's likely our download
                        if (now - mtime) < 30 and size > 10_000:
                            with open(pdf_path, "rb") as f:
                                header = f.read(4)
                            if header == b'%PDF':
                                with open(pdf_path, "rb") as f:
                                    body = f.read()
                                logger.info(f"[PDF wait] ✓ Found on disk: {len(body):,} bytes from {os.path.basename(pdf_path)}")
                                captured.append(body)
                                return True
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"[PDF wait] Disk check error: {e}")

        remaining = int(timeout_s - (time.time() - start_time))
        logger.debug(f"[PDF wait] Waiting {remaining}s...")
        time.sleep(5)

    logger.error(f"[PDF wait] ✗ Timeout after {timeout_s}s — PDF not captured")
    return bool(captured)
