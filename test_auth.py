"""
AJOG / HUJI OpenAthens auth flow test.
Tests whether plain HTTP (no browser) can authenticate and download a PDF.
Credentials are entered via secure terminal prompt - never stored or printed.
"""

import httpx
import getpass
from bs4 import BeautifulSoup

ARTICLE_URL = "https://www.ajog.org/article/S0002-9378(26)00179-1/abstract"
PDF_URL     = "https://www.ajog.org/article/S0002-9378(26)00179-1/pdf"

def step(n, msg):
    print(f"\n[Step {n}] {msg}")

def find_openathens_url(html: str, base: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "openathens" in href or "ssostart" in href or "institution" in href.lower():
            return href if href.startswith("http") else base + href
    return None

def submit_form(client, html: str, base_url: str, extra: dict = {}) -> httpx.Response:
    """Parse first <form> in page and POST it with optional overrides."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        raise ValueError("No form found on page")
    action = form.get("action", base_url)
    if not action.startswith("http"):
        from urllib.parse import urljoin
        action = urljoin(base_url, action)
    data = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name")
        if name:
            data[name] = inp.get("value", "")
    data.update(extra)
    method = form.get("method", "post").lower()
    print(f"   → {method.upper()} {action}")
    print(f"   → fields: {list(data.keys())}")
    if method == "post":
        return client.post(action, data=data)
    return client.get(action, params=data)

def run():
    print("=" * 60)
    print("AJOG / HUJI OpenAthens Auth Flow Test")
    print("=" * 60)

    email    = input("\nHUJI email address: ")
    password = getpass.getpass("HUJI password:      ")

    client = httpx.Client(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )

    # ── Step 1: Load article page ────────────────────────────────────────────
    step(1, f"Loading article page...")
    r = client.get(ARTICLE_URL)
    print(f"   → Final URL: {r.url}  [{r.status_code}]")

    # ── Step 2: Find institution access link ─────────────────────────────────
    step(2, "Looking for 'Access through institution' / OpenAthens link...")
    soup = BeautifulSoup(r.text, "html.parser")

    oa_link = None
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if any(k in href for k in ["openathens", "ssostart", "institution", "login.openathens"]):
            oa_link = href if href.startswith("http") else f"https://www.ajog.org{href}"
            print(f"   → Found: {oa_link}")
            break

    # Also try the direct ssostart endpoint Elsevier journals use
    if not oa_link:
        oa_link = "https://www.ajog.org/action/ssostart?redirectUri=%2Farticle%2FS0002-9378%2826%2900179-1%2Fpdf"
        print(f"   → Not found in page, trying known endpoint: {oa_link}")

    # ── Step 3: Navigate to OpenAthens institution selector ──────────────────
    step(3, "Following to OpenAthens institution selector...")
    r = client.get(oa_link)
    print(f"   → Final URL: {r.url}  [{r.status_code}]")

    # ── Step 4: Submit "Hebrew University" to OpenAthens ─────────────────────
    step(4, "Submitting 'Hebrew University' to OpenAthens...")
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")
    if form:
        r = submit_form(client, r.text, str(r.url), {"org": "Hebrew University of Jerusalem"})
    else:
        # OpenAthens may use a different mechanism; try known API endpoint
        print("   → No form found, trying OpenAthens search API...")
        r = client.get(
            "https://login.openathens.net/saml/2/sso/huji.ac.il",
            params={"redirectUri": PDF_URL}
        )
    print(f"   → Final URL: {r.url}  [{r.status_code}]")

    # ── Step 5: At HUJI SimpleSAML login page ───────────────────────────────
    step(5, "Checking for HUJI SimpleSAML login form...")
    if "idp.cc.huji.ac.il" not in str(r.url):
        print(f"   ⚠ Not at HUJI IdP yet. At: {r.url}")
        print("   Attempting direct HUJI IdP navigation...")
        # Try going via known HUJI/OpenAthens Shibboleth entry point
        r = client.get("https://login.openathens.net/saml/2/sso/huji.ac.il/o/70857179/c/oafed",
                       params={"redirectUri": PDF_URL})
        print(f"   → Final URL: {r.url}  [{r.status_code}]")

    # ── Step 6: Submit credentials to HUJI ──────────────────────────────────
    step(6, "Submitting credentials to HUJI IdP...")
    print(f"   → Current URL: {r.url}")
    if "loginuserpass" in str(r.url) or "huji.ac.il" in str(r.url):
        r = submit_form(client, r.text, str(r.url), {
            "username": email,
            "password": password
        })
        print(f"   → After credential submit: {r.url}  [{r.status_code}]")
    else:
        print(f"   ⚠ Not at login page. Skipping credential submit.")

    # ── Step 7: Follow SAML assertion back to AJOG ──────────────────────────
    step(7, "Following SAML assertion back to AJOG...")
    # SAML IdP often returns an auto-submit form — handle it manually
    if "SAMLResponse" in r.text or "<form" in r.text.lower():
        soup = BeautifulSoup(r.text, "html.parser")
        saml_form = soup.find("form")
        if saml_form:
            print(f"   → Found SAML response form, submitting...")
            r = submit_form(client, r.text, str(r.url))
            print(f"   → After SAML POST: {r.url}  [{r.status_code}]")

    # ── Step 8: Attempt PDF download ─────────────────────────────────────────
    step(8, "Attempting PDF download...")
    r_pdf = client.get(PDF_URL)
    print(f"   → PDF URL: {r_pdf.url}  [{r_pdf.status_code}]")
    content_type = r_pdf.headers.get("content-type", "")
    print(f"   → Content-Type: {content_type}")

    if "pdf" in content_type:
        out = "test_download.pdf"
        with open(out, "wb") as f:
            f.write(r_pdf.content)
        print(f"\n✅ SUCCESS — PDF downloaded ({len(r_pdf.content):,} bytes) → {out}")
    elif r_pdf.status_code == 200:
        print(f"\n⚠  Got 200 but Content-Type is '{content_type}' — may be a redirect/login page")
        print(f"   Final URL: {r_pdf.url}")
        # Save for inspection
        with open("test_response.html", "w", encoding="utf-8") as f:
            f.write(r_pdf.text[:5000])
        print("   First 5000 chars saved to test_response.html for inspection")
    else:
        print(f"\n❌ FAILED — HTTP {r_pdf.status_code}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    run()
