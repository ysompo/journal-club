import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/desktop", tags=["desktop"])

_GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/ysompo/journal-club/releases/latest"
)

def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@router.get("/latest")
async def get_latest_release():
    async with httpx.AsyncClient() as client:
        resp = await client.get(_GITHUB_RELEASES_URL, headers=_github_headers(), timeout=10)

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub API unavailable")

    release = resp.json()
    asset_list = release.get("assets", [])
    assets_by_name = {a["name"]: a for a in asset_list}

    msi_zip = next((a for n, a in assets_by_name.items() if n.endswith(".msi.zip") and not n.endswith(".sig")), None)
    sig_asset = next((a for n, a in assets_by_name.items() if n.endswith(".msi.zip.sig")), None)

    if not msi_zip or not sig_asset:
        raise HTTPException(status_code=404, detail="No MSI assets in latest release")

    token = os.environ.get("GITHUB_TOKEN")
    asset_headers = {"Accept": "application/octet-stream", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        asset_headers["Authorization"] = f"Bearer {token}"

    sig_api_url = f"https://api.github.com/repos/ysompo/journal-club/releases/assets/{sig_asset['id']}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        sig_resp = await client.get(sig_api_url, headers=asset_headers, timeout=10)

    return {
        "version": release["tag_name"].lstrip("v"),
        "notes": release.get("body", ""),
        "pub_date": release["published_at"],
        "platforms": {
            "windows-x86_64": {
                "signature": sig_resp.text,
                "url": msi_zip["browser_download_url"],
            }
        },
    }
