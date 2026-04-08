# Journal Club Downloader — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI tool that takes any academic journal article URL and downloads the PDF, handling institutional auth (HUJI via OpenAthens) automatically.

**Architecture:** Real Chrome launched via CDP (bypasses Cloudflare), Playwright connects to it. Publisher is detected from the URL → the matching auth flow runs → open-access is always tried first. A persistent Chrome profile caches sessions so re-auth is rare.

**Tech Stack:** Python 3.11+, Playwright sync_api (CDP mode), PyYAML, real Google Chrome

---

## File Structure

```
journal_club/
  __init__.py          # empty
  config.py            # load config.yaml → dataclass Config
  browser.py           # launch Chrome + connect CDP + cleanup
  pdf_capture.py       # register response/download hooks, return bytes
  huji_login.py        # HUJI IdP login (reusable across all flows)
  auth_oa_check.py     # open-access: try direct PDF link before any auth
  auth_openathens.py   # generic OpenAthens wayfinder (NEJM, BMJ, Wiley…)
  auth_jama.py         # JAMA Silverchair → JAMA institution search → OA/HUJI
  auth_ovid.py         # LWW/Ovid → Ovid institution selector → wayfinder → HUJI
  auth_elsevier.py     # Elsevier ScienceDirect/AJOG → OA → institution → HUJI
  router.py            # URL pattern → auth module dispatch
download.py            # CLI entry point: python download.py <url>
config.yaml            # credentials + output_dir + chrome_path
tests/
  test_config.py
  test_router.py
```

---

## Task 1: Project skeleton + config

**Files:**
- Create: `journal_club/__init__.py`
- Create: `journal_club/config.py`
- Create: `config.yaml`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest, os, textwrap, tempfile
from journal_club.config import load_config

def test_load_config_reads_fields(tmp_path):
    yaml_text = textwrap.dedent("""\
        huji_email: user@mail.huji.ac.il
        huji_password: secret123
        output_dir: /tmp/pdfs
        chrome_profile: /tmp/chrome-jc
    """)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    cfg = load_config(str(cfg_file))
    assert cfg.huji_email == "user@mail.huji.ac.il"
    assert cfg.huji_password == "secret123"
    assert cfg.output_dir == "/tmp/pdfs"

def test_load_config_missing_key_raises(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("huji_email: x\n")
    with pytest.raises(KeyError):
        load_config(str(cfg_file))
```

- [ ] **Step 2: Run test to confirm it fails**

```
cd "C:\Users\ysomp\OneDrive\Documents\Journal Club"
python -m pytest tests/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'journal_club'`

- [ ] **Step 3: Create `journal_club/__init__.py`**

```python
# journal_club/__init__.py
```
(empty file)

- [ ] **Step 4: Create `journal_club/config.py`**

```python
# journal_club/config.py
from dataclasses import dataclass
import yaml

@dataclass
class Config:
    huji_email: str
    huji_password: str
    output_dir: str
    chrome_profile: str
    chrome_path: str = ""   # optional override; auto-detected if empty

def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(
        huji_email=data["huji_email"],
        huji_password=data["huji_password"],
        output_dir=data["output_dir"],
        chrome_profile=data["chrome_profile"],
        chrome_path=data.get("chrome_path", ""),
    )
```

- [ ] **Step 5: Create `config.yaml`**

```yaml
# Fill in your HUJI credentials before running
huji_email: "your_email@mail.huji.ac.il"
huji_password: "your_password"
output_dir: "C:\\Users\\ysomp\\OneDrive\\Documents\\Journal Club\\downloads"
chrome_profile: "C:\\Temp\\chrome-journal-club"
# chrome_path: ""   # leave empty to auto-detect
```

- [ ] **Step 6: Run tests to confirm they pass**

```
python -m pytest tests/test_config.py -v
```
Expected: 2 passed

- [ ] **Step 7: Commit**

```
git add journal_club/__init__.py journal_club/config.py config.yaml tests/test_config.py
git commit -m "feat: config module with YAML loading"
```

---

## Task 2: Publisher router

**Files:**
- Create: `journal_club/router.py`
- Create: `tests/test_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router.py
import pytest
from journal_club.router import detect_publisher, Publisher

@pytest.mark.parametrize("url,expected", [
    ("https://jamanetwork.com/journals/jama/article-abstract/2844116", Publisher.JAMA),
    ("https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/123", Publisher.JAMA),
    ("https://journals.lww.com/greenjournal/citation/2026/04001/foo.aspx", Publisher.OVID),
    ("https://ovidsp.ovid.com/ovidweb.cgi?T=JS&PAGE=reference&D=med24", Publisher.OVID),
    ("https://www.sciencedirect.com/science/article/pii/S0140673624001234", Publisher.ELSEVIER),
    ("https://www.ajog.org/article/S0002-9378(24)00123-4/fulltext", Publisher.ELSEVIER),
    ("https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(24)00001-X/fulltext", Publisher.ELSEVIER),
    ("https://www.nature.com/articles/s41591-026-04256-2", Publisher.SPRINGER_NATURE),
    ("https://link.springer.com/article/10.1007/s00404-024-01234-5", Publisher.SPRINGER_NATURE),
    ("https://www.nejm.org/doi/full/10.1056/NEJMoa2400001", Publisher.OPENATHENS_GENERIC),
    ("https://www.bmj.com/content/385/bmj.q1234", Publisher.OPENATHENS_GENERIC),
    ("https://academic.oup.com/jcem/article/109/1/1/1234567", Publisher.OPENATHENS_GENERIC),
    ("https://onlinelibrary.wiley.com/doi/10.1111/jog.12345", Publisher.OPENATHENS_GENERIC),
    ("https://www.thieme-connect.com/products/ejournals/abstract/1234", Publisher.OPENATHENS_GENERIC),
    ("https://www.annualreviews.org/doi/abs/10.1146/annurev-001", Publisher.OPENATHENS_GENERIC),
])
def test_detect_publisher(url, expected):
    assert detect_publisher(url) == expected
```

- [ ] **Step 2: Run test to confirm it fails**

```
python -m pytest tests/test_router.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Create `journal_club/router.py`**

```python
# journal_club/router.py
from enum import Enum, auto

class Publisher(Enum):
    JAMA              = auto()
    OVID              = auto()
    ELSEVIER          = auto()
    SPRINGER_NATURE   = auto()
    OPENATHENS_GENERIC = auto()

_RULES: list[tuple[list[str], Publisher]] = [
    # Match most-specific first
    (["jamanetwork.com"],                          Publisher.JAMA),
    (["journals.lww.com", "ovidsp.ovid.com",
      "ovid.com"],                                 Publisher.OVID),
    (["sciencedirect.com", "ajog.org",
      "thelancet.com", "cell.com",
      "elsevier.com"],                             Publisher.ELSEVIER),
    (["nature.com", "link.springer.com",
      "springer.com"],                             Publisher.SPRINGER_NATURE),
    # Generic OpenAthens / Shibboleth — catch-all for the rest
    (["nejm.org", "bmj.com",
      "academic.oup.com", "onlinelibrary.wiley.com",
      "thieme-connect.com", "annualreviews.org",
      "tandfonline.com", "karger.com",
      "acog.org"],                                 Publisher.OPENATHENS_GENERIC),
]

def detect_publisher(url: str) -> Publisher:
    for domains, publisher in _RULES:
        if any(d in url for d in domains):
            return publisher
    return Publisher.OPENATHENS_GENERIC   # best-effort fallback
```

- [ ] **Step 4: Run tests**

```
python -m pytest tests/test_router.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```
git add journal_club/router.py tests/test_router.py
git commit -m "feat: publisher router with URL pattern matching"
```

---

## Task 3: Browser module

**Files:**
- Create: `journal_club/browser.py`

No unit tests for this module — it wraps subprocess + Playwright which require a live Chrome install. Tested implicitly by later integration tasks.

- [ ] **Step 1: Create `journal_club/browser.py`**

```python
# journal_club/browser.py
import os
import subprocess
import time
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

def find_chrome(override: str = "") -> str:
    if override and os.path.exists(override):
        return override
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Google Chrome not found. Install Chrome or set chrome_path in config.yaml")


@contextmanager
def launch_browser(profile_dir: str, chrome_path: str = "", port: int = 9222,
                   start_url: str = "about:blank"):
    """
    Context manager: launches Chrome with remote debugging, yields (playwright, browser, context, page).
    Cleans up on exit.
    """
    os.makedirs(profile_dir, exist_ok=True)
    chrome = find_chrome(chrome_path)

    proc = subprocess.Popen([
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ])
    time.sleep(4)   # wait for Chrome DevTools protocol to become available

    with sync_playwright() as p:
        browser: Browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
        context: BrowserContext = browser.contexts[0] if browser.contexts else browser.new_context()
        pages = context.pages
        page: Page = pages[0] if pages else context.new_page()
        try:
            yield p, browser, context, page
        finally:
            try:
                browser.close()
            except Exception:
                pass
            proc.terminate()
```

- [ ] **Step 2: Commit**

```
git add journal_club/browser.py
git commit -m "feat: browser launch/connect context manager"
```

---

## Task 4: PDF capture utility

**Files:**
- Create: `journal_club/pdf_capture.py`

- [ ] **Step 1: Create `journal_club/pdf_capture.py`**

```python
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
    print(f"   Saved → {out_path} ({os.path.getsize(out_path):,} bytes)")
    return True


def wait_for_pdf(captured: list, timeout_s: int = 30) -> bool:
    """Poll until PDF is captured or timeout. Returns True if captured."""
    for remaining in range(timeout_s, 0, -5):
        if captured:
            return True
        print(f"   ... waiting {remaining}s")
        time.sleep(5)
    return bool(captured)
```

- [ ] **Step 2: Commit**

```
git add journal_club/pdf_capture.py
git commit -m "feat: PDF capture hooks (response + download interception)"
```

---

## Task 5: HUJI login handler

**Files:**
- Create: `journal_club/huji_login.py`

- [ ] **Step 1: Create `journal_club/huji_login.py`**

```python
# journal_club/huji_login.py
import time
from playwright.sync_api import Page

def dismiss_cookies(page: Page, timeout_ms: int = 3000):
    """Try common cookie banner dismiss buttons."""
    for sel in [
        "button:has-text('Accept all cookies')",
        "button:has-text('Accept all')",
        "button:has-text('Accept necessary cookies')",
        "button:has-text('Accept')",
        "button:has-text('I agree')",
        "button:has-text('OK')",
    ]:
        try:
            page.click(sel, timeout=timeout_ms)
            time.sleep(0.5)
            return
        except Exception:
            continue


def login_huji(page: Page, email: str, password: str, manual_timeout_s: int = 20):
    """
    Assumes page is already on the HUJI IdP (idp.cc.huji.ac.il).
    Clicks the "With E-mail password" tab, fills credentials, submits.
    Falls back to manual wait if selectors fail.
    """
    print(f"   [HUJI] On: {page.url[:60]}")

    # Click "With E-mail password" tab
    for sel in [
        "text=With E-mail password",
        "button:has-text('E-mail password')",
        "a:has-text('E-mail password')",
        "[role='tab']:has-text('E-mail')",
    ]:
        try:
            page.click(sel, timeout=4000)
            print("   [HUJI] Clicked email tab")
            time.sleep(1)
            break
        except Exception:
            continue

    # Fill email
    for sel in ['input[type="email"]', 'input[name="username"]', '#username',
                'input[placeholder*="mail"]']:
        try:
            existing = page.input_value(sel)
            if not existing:
                page.fill(sel, email, timeout=3000)
            print(f"   [HUJI] Email ready")
            break
        except Exception:
            continue

    # Fill password
    for sel in ['input[type="password"]', 'input[name="password"]', '#password']:
        try:
            page.fill(sel, password, timeout=3000)
            print(f"   [HUJI] Password filled")
            break
        except Exception:
            continue

    # Submit
    for sel in ['button:has-text("Enter")', 'button[type="submit"]',
                'input[type="submit"]', 'button:has-text("Log in")']:
        try:
            page.click(sel, timeout=3000)
            print(f"   [HUJI] Submitted")
            return
        except Exception:
            continue

    print(f"   [HUJI] Auto-submit failed — waiting {manual_timeout_s}s for manual login")
    time.sleep(manual_timeout_s)


def wait_for_huji_and_login(page: Page, email: str, password: str,
                             arrive_timeout_ms: int = 30_000):
    """
    Wait for page to navigate to huji.ac.il, then call login_huji().
    """
    try:
        page.wait_for_function(
            "() => window.location.href.includes('huji.ac.il')",
            timeout=arrive_timeout_ms,
        )
        time.sleep(1)
        login_huji(page, email, password)
    except Exception as e:
        print(f"   [HUJI] Did not reach HUJI login: {e}")
        time.sleep(20)
```

- [ ] **Step 2: Commit**

```
git add journal_club/huji_login.py
git commit -m "feat: reusable HUJI IdP login handler"
```

---

## Task 6: Open-access checker

**Files:**
- Create: `journal_club/auth_oa_check.py`

This is **always called first** before any auth flow. It looks for a PDF link directly in the DOM of the article page. If the link loads a valid PDF (checked by response hook), auth is skipped entirely.

- [ ] **Step 1: Create `journal_club/auth_oa_check.py`**

```python
# journal_club/auth_oa_check.py
"""
Open-access check: try to find + navigate to a PDF link directly in the DOM.
Must be called BEFORE any auth flow.
Returns True if PDF was captured (open access confirmed).
"""
import time
from playwright.sync_api import Page, BrowserContext

from journal_club.pdf_capture import wait_for_pdf

_PDF_LINK_JS = """
() => {
    const links = Array.from(document.querySelectorAll('a[href]'));
    const pdf = links.find(a =>
        (a.href.endsWith('.pdf') || a.href.includes('/pdf') || a.href.includes('pdf=1')) &&
        (a.innerText || a.textContent || '').toLowerCase().includes('pdf')
    );
    return pdf ? pdf.href : null;
}
"""

def check_open_access(page: Page, context: BrowserContext,
                      captured: list, timeout_s: int = 15) -> bool:
    """
    Navigate to article_url (already loaded on page), look for a direct PDF link.
    If found, open it in a new tab and wait for PDF capture.
    Returns True if a PDF was captured.
    """
    print("\n[OA Check] Scanning DOM for direct PDF link...")

    pdf_href: str | None = None
    try:
        pdf_href = page.evaluate(_PDF_LINK_JS)
    except Exception as e:
        print(f"   [OA Check] JS eval error: {e}")

    if not pdf_href:
        print("   [OA Check] No direct PDF link found.")
        return False

    print(f"   [OA Check] Found PDF link: {pdf_href[:80]}")
    try:
        pdf_tab = context.new_page()
        pdf_tab.on("response", lambda r: None)   # hooks already attached via context
        pdf_tab.goto(pdf_href, wait_until="commit", timeout=20_000)
        time.sleep(8)
        print(f"   [OA Check] Tab landed on: {pdf_tab.url[:80]}")
    except Exception as e:
        print(f"   [OA Check] Navigation error: {e}")

    if captured:
        print("   [OA Check] Open access confirmed — PDF captured!")
        return True

    print("   [OA Check] PDF not accessible without auth.")
    return False
```

- [ ] **Step 2: Commit**

```
git add journal_club/auth_oa_check.py
git commit -m "feat: open-access check (DOM PDF link scan)"
```

---

## Task 7: JAMA auth flow

**Files:**
- Create: `journal_club/auth_jama.py`

Proven flow from `test_jama.py`:
1. Navigate directly to Shibboleth URL (skips popups)
2. Type "Hebrew University" in `input.js-sa-institution-search` using `page.type()` (not fill)
3. Wait 3s → click `a.sa-institutionslink`
4. If OpenAthens intermediate appears: dismiss cookies → type institution → click result
5. Wait for HUJI → login
6. Wait for return to JAMA → navigate to fulltext → click Download PDF

- [ ] **Step 1: Create `journal_club/auth_jama.py`**

```python
# journal_club/auth_jama.py
import time
from urllib.parse import quote
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def _build_shibboleth_url(article_url: str) -> str:
    """Return the JAMA Shibboleth login URL that redirects back to the given article."""
    # Convert abstract URL to fulltext URL for return target
    return_url = article_url.replace("article-abstract", "fullarticle")
    encoded = quote(return_url, safe="")
    return f"https://jamanetwork.com/signinshibboleth?returnUrl={encoded}"

def _select_huji_on_jama(page: Page):
    """Type Hebrew University in the JAMA institution search and click the result."""
    print("   [JAMA] Selecting HUJI institution...")
    page.click("input.js-sa-institution-search", timeout=10_000)
    page.type("input.js-sa-institution-search", "Hebrew University", delay=50)
    time.sleep(3)
    page.click("a.sa-institutionslink", timeout=10_000)
    print("   [JAMA] Selected Hebrew University of Jerusalem")
    time.sleep(2)
    print(f"   [JAMA] On: {page.url[:80]}")

def _handle_openathens_intermediate(page: Page):
    """
    If page lands on login.openathens.net, dismiss cookies, search for HUJI, click result.
    """
    if "openathens" not in page.url:
        return
    print("   [JAMA] OpenAthens intermediate detected")
    dismiss_cookies(page)
    time.sleep(1)

    for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                'input[placeholder*="rganiz"]', 'input[name="institution"]',
                'input[type="search"]', 'input[type="text"]']:
        try:
            page.click(sel, timeout=3000)
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [JAMA/OA] Typed institution: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

    for sel in [
        "li:has-text('Hebrew University')",
        "[role='option']:has-text('Hebrew')",
        "a:has-text('Hebrew University')",
        "button:has-text('Hebrew University')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [JAMA/OA] Clicked institution result: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

def authenticate_jama(page: Page, article_url: str, email: str, password: str,
                      captured: list):
    """Full JAMA auth flow. Assumes PDF hooks already attached to page/context."""
    shib_url = _build_shibboleth_url(article_url)
    print(f"\n[JAMA Auth] Navigating to Shibboleth URL...")
    page.goto(shib_url, wait_until="domcontentloaded")
    time.sleep(2)
    print(f"   On: {page.url[:80]}")

    _select_huji_on_jama(page)

    # May land on OpenAthens intermediate before HUJI
    try:
        page.wait_for_function(
            "() => window.location.href.includes('huji.ac.il') || window.location.href.includes('openathens')",
            timeout=30_000,
        )
        _handle_openathens_intermediate(page)
    except Exception as e:
        print(f"   [JAMA Auth] Timeout waiting for HUJI/OA: {e}")

    wait_for_huji_and_login(page, email, password)

    # Wait to return to JAMA
    print("\n[JAMA Auth] Waiting to return to JAMA...")
    try:
        page.wait_for_function(
            """() => window.location.href.includes('jamanetwork.com') &&
                     !window.location.href.includes('login') &&
                     !window.location.href.includes('idp')""",
            timeout=90_000,
        )
        print(f"   Back on JAMA: {page.url}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)

    # Navigate to fulltext page
    ft_url = article_url.replace("article-abstract", "fullarticle")
    page.goto(ft_url, wait_until="domcontentloaded")
    time.sleep(3)

    # Click Download PDF
    print("\n[JAMA Auth] Clicking Download PDF...")
    for sel in [
        "a:has-text('Download PDF')",
        "button:has-text('Download PDF')",
        "[aria-label*='Download PDF']",
        "a[data-article-action='download-pdf']",
        ".article-tools__item--pdf a",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   Clicked: {sel}")
            break
        except Exception:
            continue
```

- [ ] **Step 2: Commit**

```
git add journal_club/auth_jama.py
git commit -m "feat: JAMA Silverchair auth flow"
```

---

## Task 8: LWW/Ovid auth flow

**Files:**
- Create: `journal_club/auth_ovid.py`

Proven flow from `test_lww.py`:
1. Navigate to article fulltext — check OA first (hooks already set up by caller)
2. If blocked: go to Ovid login page → click OpenAthens/Institutional
3. On wayfinder.openathens.net: type institution → click `span:has-text('Hebrew University of Jerusalem')`
4. HUJI login → return to LWW
5. Click Download (dropdown) → then PDF button

- [ ] **Step 1: Create `journal_club/auth_ovid.py`**

```python
# journal_club/auth_ovid.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login

def _build_ovid_login_url(article_url: str) -> str:
    """Build the Ovid direct-login URL based on the article domain."""
    # LWW journals use journals.lww.com → login at ovid
    if "journals.lww.com" in article_url:
        return "https://ovidsp.ovid.com/autologin.asp?site=ovidweb.cgi&resource=journals"
    return "https://ovidsp.ovid.com/autologin.asp"

def _select_institution_on_wayfinder(page: Page):
    """On wayfinder.openathens.net: type HUJI and click the result span."""
    print("   [Ovid] On wayfinder — searching for HUJI...")
    for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                'input[name="institution"]', 'input[type="search"]', 'input[type="text"]']:
        try:
            page.click(sel, timeout=3000)
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [Ovid] Typed institution: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

    # The wayfinder result is a SPAN with class wayfinder-item-displayname-text
    for sel in [
        "span:has-text('Hebrew University of Jerusalem')",
        "button:has-text('Hebrew University')",
        "li:has-text('Hebrew University')",
        "[role='option']:has-text('Hebrew')",
        "a:has-text('Hebrew University')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Ovid] Selected institution: {sel}")
            time.sleep(2)
            return
        except Exception:
            continue
    print("   [Ovid] Could not click wayfinder result — check selectors")

def authenticate_ovid(page: Page, article_url: str, email: str, password: str,
                      captured: list):
    """Full LWW/Ovid auth flow."""
    # Construct direct Ovid login URL
    ovid_url = _build_ovid_login_url(article_url)
    print(f"\n[Ovid Auth] Navigating to Ovid login: {ovid_url[:60]}")
    page.goto(ovid_url, wait_until="domcontentloaded")
    time.sleep(3)
    print(f"   On: {page.url[:80]}")

    # Click "OpenAthens/Institutional login"
    for sel in [
        "a:has-text('OpenAthens')",
        "button:has-text('OpenAthens')",
        "a:has-text('Institutional')",
        "a:has-text('Institution')",
        "[data-target*='openathens']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Ovid] Clicked: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue

    print(f"   On: {page.url[:80]}")

    # Wait for wayfinder or HUJI
    try:
        page.wait_for_function(
            "() => window.location.href.includes('wayfinder') || window.location.href.includes('huji.ac.il')",
            timeout=20_000,
        )
        if "wayfinder" in page.url:
            _select_institution_on_wayfinder(page)
    except Exception as e:
        print(f"   [Ovid] Timeout waiting for wayfinder: {e}")

    wait_for_huji_and_login(page, email, password)

    # Wait to return to LWW
    print("\n[Ovid Auth] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => (window.location.href.includes('lww.com') ||
                      window.location.href.includes('ovid.com')) &&
                     !window.location.href.includes('login')""",
            timeout=90_000,
        )
        print(f"   Back on journal: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)

    # Click Download (opens dropdown) → PDF
    print("\n[Ovid Auth] Clicking Download PDF...")
    for download_sel in [
        "button:has-text('Download')",
        "a:has-text('Download')",
    ]:
        try:
            page.click(download_sel, timeout=5000)
            print(f"   Clicked download toggle: {download_sel}")
            time.sleep(1)
            break
        except Exception:
            continue

    for pdf_sel in [
        "button:has-text('PDF')",
        "a:has-text('PDF')",
        "li:has-text('PDF')",
    ]:
        try:
            page.click(pdf_sel, timeout=5000)
            print(f"   Clicked PDF: {pdf_sel}")
            break
        except Exception:
            continue
```

- [ ] **Step 2: Commit**

```
git add journal_club/auth_ovid.py
git commit -m "feat: LWW/Ovid auth flow via OpenAthens wayfinder"
```

---

## Task 9: Generic OpenAthens auth flow

**Files:**
- Create: `journal_club/auth_openathens.py`

Covers: NEJM, BMJ, OUP, Wiley, T&F, Thieme, Annals, and any other journal that uses an "Access through institution" → OpenAthens wayfinder → HUJI pattern.

- [ ] **Step 1: Create `journal_club/auth_openathens.py`**

```python
# journal_club/auth_openathens.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def _click_access_through_institution(page: Page):
    for sel in [
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('Log in via your institution')",
        "a:has-text('Institutional access')",
        "a:has-text('Log in')",
        "button:has-text('Log in')",
        "[data-test='institution-login']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [OA Generic] Clicked: {sel}")
            time.sleep(3)
            return
        except Exception:
            continue
    print("   [OA Generic] No institution login button found")

def _select_huji_on_wayfinder(page: Page):
    """Type HUJI and select from wayfinder or OpenAthens dropdown."""
    dismiss_cookies(page)
    time.sleep(1)

    for sel in ['input[placeholder*="nstitut"]', 'input[placeholder*="niversit"]',
                'input[placeholder*="rganiz"]', 'input[name="org"]',
                'input[type="search"]', 'input[type="text"]']:
        try:
            page.click(sel, timeout=3000)
            page.type(sel, "Hebrew University of Jerusalem", delay=50)
            print(f"   [OA Generic] Typed institution: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

    for sel in [
        "span:has-text('Hebrew University of Jerusalem')",   # wayfinder SPAN
        "li:has-text('Hebrew University')",
        "[role='option']:has-text('Hebrew')",
        "a:has-text('Hebrew University')",
        "button:has-text('Hebrew University')",
        ".result:has-text('Hebrew')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [OA Generic] Selected institution: {sel}")
            time.sleep(2)
            return
        except Exception:
            continue
    print("   [OA Generic] Could not find institution result — may need manual selection")

def authenticate_openathens(page: Page, article_url: str, email: str, password: str,
                             captured: list):
    """Generic OpenAthens auth flow for NEJM, BMJ, OUP, Wiley, etc."""
    print(f"\n[OA Generic Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(2)

    # Dismiss cookie banner on article page
    dismiss_cookies(page)

    _click_access_through_institution(page)
    print(f"   On: {page.url[:80]}")

    # Wait for wayfinder, OpenAthens, or HUJI
    try:
        page.wait_for_function(
            """() => window.location.href.includes('wayfinder') ||
                     window.location.href.includes('openathens') ||
                     window.location.href.includes('huji.ac.il')""",
            timeout=30_000,
        )
        current = page.url
        if "wayfinder" in current or "openathens" in current:
            _select_huji_on_wayfinder(page)
    except Exception as e:
        print(f"   [OA Generic] Timeout waiting for auth page: {e}")

    wait_for_huji_and_login(page, email, password)

    # Wait to return to journal
    print("\n[OA Generic] Waiting to return to journal...")
    try:
        page.wait_for_function(
            f"""() => {{
                const url = window.location.href;
                return !url.includes('huji.ac.il') &&
                       !url.includes('openathens') &&
                       !url.includes('wayfinder') &&
                       !url.includes('login');
            }}""",
            timeout=90_000,
        )
        print(f"   Back on journal: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)

    # Click Download PDF (generic attempt)
    for sel in [
        "a:has-text('Download PDF')",
        "button:has-text('Download PDF')",
        "a:has-text('PDF')",
        "[aria-label*='PDF']",
        "a[href$='.pdf']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   Clicked: {sel}")
            break
        except Exception:
            continue
```

- [ ] **Step 2: Commit**

```
git add journal_club/auth_openathens.py
git commit -m "feat: generic OpenAthens auth flow (NEJM, BMJ, Wiley, etc.)"
```

---

## Task 10: Elsevier auth flow

**Files:**
- Create: `journal_club/auth_elsevier.py`

Elsevier (ScienceDirect, AJOG, Lancet) uses Cloudflare — must use real Chrome.
Flow: article page → "Get access" → "Access through your institution" → OpenAthens → HUJI.
PDF is found via DOM after auth (not intercepted via response — Elsevier serves PDF in viewer).

- [ ] **Step 1: Create `journal_club/auth_elsevier.py`**

```python
# journal_club/auth_elsevier.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def _extract_pdf_url_from_dom(page: Page) -> str | None:
    """Look for the actual PDF download link in the authenticated Elsevier page."""
    return page.evaluate("""
        () => {
            // ScienceDirect PDF download link
            const links = Array.from(document.querySelectorAll('a[href]'));
            const pdf = links.find(a =>
                (a.href.includes('pdfft') || a.href.includes('/pdf/') ||
                 a.href.endsWith('.pdf')) &&
                (a.innerText || a.textContent || '').toLowerCase().includes('pdf')
            );
            return pdf ? pdf.href : null;
        }
    """)

def authenticate_elsevier(page: Page, article_url: str, email: str, password: str,
                           captured: list):
    """Elsevier/ScienceDirect auth flow."""
    print(f"\n[Elsevier Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    dismiss_cookies(page)

    # Click "Get access" or "Access through institution"
    for sel in [
        "text=Get access",
        "button:has-text('Get access')",
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('Institutional access')",
        "#access-options",
        "button.buybox__btn",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked: {sel}")
            time.sleep(2)
            break
        except Exception:
            continue

    # May show a modal/dropdown — click "Access through your institution" inside it
    for sel in [
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('institution')",
        "a[href*='openathens']",
        "a[href*='shibboleth']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked institution link: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue

    print(f"   On: {page.url[:80]}")

    # Wait for OpenAthens / wayfinder / HUJI
    try:
        page.wait_for_function(
            """() => window.location.href.includes('wayfinder') ||
                     window.location.href.includes('openathens') ||
                     window.location.href.includes('huji.ac.il')""",
            timeout=30_000,
        )
        current = page.url
        if "wayfinder" in current or "openathens" in current:
            dismiss_cookies(page)
            time.sleep(1)
            for sel in ['input[placeholder*="nstitut"]', 'input[type="search"]', 'input[type="text"]']:
                try:
                    page.click(sel, timeout=3000)
                    page.type(sel, "Hebrew University of Jerusalem", delay=50)
                    time.sleep(2)
                    break
                except Exception:
                    continue
            for sel in [
                "span:has-text('Hebrew University of Jerusalem')",
                "li:has-text('Hebrew University')",
                "a:has-text('Hebrew University')",
                "[role='option']:has-text('Hebrew')",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    time.sleep(2)
                    break
                except Exception:
                    continue
    except Exception as e:
        print(f"   [Elsevier] Timeout: {e}")

    wait_for_huji_and_login(page, email, password)

    # Wait to return to journal
    print("\n[Elsevier] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => !window.location.href.includes('huji.ac.il') &&
                     !window.location.href.includes('openathens') &&
                     !window.location.href.includes('login')""",
            timeout=90_000,
        )
        print(f"   Back: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)

    # Click Download PDF
    for sel in [
        "a:has-text('Download PDF')",
        "button:has-text('Download PDF')",
        "a[href*='pdfft']",
        "a[href$='.pdf']",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Elsevier] Clicked: {sel}")
            break
        except Exception:
            continue
```

- [ ] **Step 2: Commit**

```
git add journal_club/auth_elsevier.py
git commit -m "feat: Elsevier/ScienceDirect auth flow"
```

---

## Task 11: SpringerNature auth flow

**Files:**
- Create: `journal_club/auth_springer.py`

SpringerNature (nature.com, link.springer.com): open access articles deliver PDF directly.
Subscription articles go through SpringerNature gateway → OpenAthens → HUJI.
The OA check in Task 6 handles the OA case. This module handles the subscription case.

- [ ] **Step 1: Create `journal_club/auth_springer.py`**

```python
# journal_club/auth_springer.py
import time
from playwright.sync_api import Page

from journal_club.huji_login import wait_for_huji_and_login, dismiss_cookies

def authenticate_springer(page: Page, article_url: str, email: str, password: str,
                           captured: list):
    """SpringerNature subscription auth flow (used only if OA check failed)."""
    print(f"\n[Springer Auth] Article: {article_url[:60]}")
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)
    dismiss_cookies(page)

    for sel in [
        "a:has-text('Access through your institution')",
        "button:has-text('Access through your institution')",
        "a:has-text('Log in via your institution')",
        "a:has-text('Log in')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Springer] Clicked: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue

    # SpringerNature gateway may have another "Access through institution" button
    for sel in [
        "a:has-text('Access through your institution')",
        "a:has-text('institution')",
        "a:has-text('Shibboleth')",
        "a:has-text('OpenAthens')",
        "[data-test='institution-login']",
    ]:
        try:
            page.click(sel, timeout=3000)
            print(f"   [Springer] Gateway click: {sel}")
            time.sleep(3)
            break
        except Exception:
            continue

    print(f"   On: {page.url[:80]}")

    # Wait for OpenAthens/wayfinder/HUJI
    try:
        page.wait_for_function(
            """() => window.location.href.includes('wayfinder') ||
                     window.location.href.includes('openathens') ||
                     window.location.href.includes('huji.ac.il')""",
            timeout=30_000,
        )
        if "wayfinder" in page.url or "openathens" in page.url:
            dismiss_cookies(page)
            time.sleep(1)
            for sel in ['input[placeholder*="nstitut"]', 'input[type="search"]',
                        'input.js-sa-institution-search', 'input[type="text"]']:
                try:
                    page.click(sel, timeout=3000)
                    page.type(sel, "Hebrew University of Jerusalem", delay=50)
                    time.sleep(2)
                    break
                except Exception:
                    continue
            for sel in [
                "span:has-text('Hebrew University of Jerusalem')",
                "li:has-text('Hebrew University')",
                "a:has-text('Hebrew University')",
                "a.sa-institutionslink",
            ]:
                try:
                    page.click(sel, timeout=5000)
                    time.sleep(2)
                    break
                except Exception:
                    continue
    except Exception as e:
        print(f"   [Springer] Timeout: {e}")

    wait_for_huji_and_login(page, email, password)

    print("\n[Springer] Waiting to return to journal...")
    try:
        page.wait_for_function(
            """() => !window.location.href.includes('huji.ac.il') &&
                     !window.location.href.includes('openathens') &&
                     !window.location.href.includes('login')""",
            timeout=90_000,
        )
        print(f"   Back: {page.url[:80]}")
    except Exception:
        print(f"   Timeout. URL: {page.url}")

    time.sleep(3)
    page.goto(article_url, wait_until="domcontentloaded")
    time.sleep(3)

    for sel in [
        "a:has-text('Download PDF')",
        "button:has-text('Download PDF')",
        "a[href$='.pdf']",
        "a:has-text('PDF')",
    ]:
        try:
            page.click(sel, timeout=5000)
            print(f"   [Springer] Clicked: {sel}")
            break
        except Exception:
            continue
```

- [ ] **Step 2: Commit**

```
git add journal_club/auth_springer.py
git commit -m "feat: SpringerNature subscription auth flow"
```

---

## Task 12: CLI entry point (`download.py`)

**Files:**
- Create: `download.py`

This is the main entry point. Usage: `python download.py <article_url>`

Flow:
1. Load config
2. Launch Chrome
3. Navigate to article URL
4. Attach PDF capture hooks
5. Run OA check (always first)
6. If no PDF yet: route to publisher-specific auth flow
7. Wait for PDF capture
8. Save PDF to `output_dir/<article_slug>.pdf`

- [ ] **Step 1: Create `download.py`**

```python
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

        if check_open_access(page, context, captured, timeout_s=20):
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

            wait_for_pdf(captured, timeout_s=30)

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
```

- [ ] **Step 2: Run a quick smoke test (no auth, just router + OA check path)**

Open a known OA article:
```
python download.py "https://www.nature.com/articles/s41591-026-04256-2"
```
Expected: OA check finds PDF link → PDF captured → saved to downloads folder.

- [ ] **Step 3: Commit**

```
git add download.py
git commit -m "feat: CLI entry point with OA-first routing"
```

---

## Task 13: Integration test — JAMA

- [ ] **Step 1: Run end-to-end test on a JAMA article**

```
python download.py "https://jamanetwork.com/journals/jama/article-abstract/2844116"
```
Expected: auth flow completes → PDF saved → file > 100KB.

- [ ] **Step 2: Verify file**

```
ls -lh downloads/
```
Confirm PDF exists and is > 100KB.

- [ ] **Step 3: Commit notes** (no code changes unless fixes needed)

```
git commit -m "test: JAMA integration verified" --allow-empty
```

---

## Task 14: Integration test — LWW/Ovid

- [ ] **Step 1: Run end-to-end on an LWW article**

```
python download.py "https://journals.lww.com/greenjournal/citation/2026/04001/artificial_intelligence_based_risk_calculator_for.4.aspx"
```
Expected: OA check or Ovid auth → PDF captured.

- [ ] **Step 2: Commit (with any fixes)**

```
git add -u
git commit -m "test: LWW/Ovid integration verified"
```

---

## Task 15: Integration test — Nature (OA)

- [ ] **Step 1: Run on OA Nature article**

```
python download.py "https://www.nature.com/articles/s41591-026-04256-2"
```
Expected: OA check succeeds immediately — no auth needed.

- [ ] **Step 2: Commit**

```
git commit -m "test: Nature open-access verified" --allow-empty
```

---

## Self-Review

**Spec coverage:**
- ✅ OA check before auth (Task 6)
- ✅ Publisher routing (Task 2)
- ✅ JAMA flow (Task 7)
- ✅ LWW/Ovid flow (Task 8)
- ✅ Elsevier flow (Task 10)
- ✅ SpringerNature flow (Task 11)
- ✅ Generic OpenAthens for NEJM/BMJ/Wiley/OUP/etc. (Task 9)
- ✅ HUJI login reusable handler (Task 5)
- ✅ PDF capture (Task 4)
- ✅ Chrome launch/connect (Task 3)
- ✅ CLI entry point (Task 12)
- ✅ Config with credentials (Task 1)
- ✅ Persistent Chrome profile (via `chrome_profile` in config)

**No placeholders detected.**

**Type consistency:** `captured: list[bytes]` used consistently as the shared mutable list across all modules. `Config` dataclass matches fields in `load_config`. `auth_kwargs` dict keys match function signatures.
