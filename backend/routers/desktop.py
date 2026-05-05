import os
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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

def _asset_headers() -> dict:
    headers = {
        "Accept": "application/octet-stream",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _get_latest_release_data():
    async with httpx.AsyncClient() as client:
        resp = await client.get(_GITHUB_RELEASES_URL, headers=_github_headers(), timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub API unavailable")
    release = resp.json()
    assets_by_name = {a["name"]: a for a in release.get("assets", [])}

    msi_zip = next((a for n, a in assets_by_name.items() if n.endswith(".msi.zip") and not n.endswith(".sig")), None)
    msi_sig = next((a for n, a in assets_by_name.items() if n.endswith(".msi.zip.sig")), None)
    mac_tar = next((a for n, a in assets_by_name.items() if n.endswith(".app.tar.gz") and not n.endswith(".sig")), None)
    mac_sig = next((a for n, a in assets_by_name.items() if n.endswith(".app.tar.gz.sig")), None)

    return release, msi_zip, msi_sig, mac_tar, mac_sig


@router.get("/latest")
async def get_latest_release():
    release, msi_zip, msi_sig, mac_tar, mac_sig = await _get_latest_release_data()

    version = release["tag_name"].lstrip("v")
    platforms = {}

    async def fetch_sig(asset):
        url = f"https://api.github.com/repos/ysompo/journal-club/releases/assets/{asset['id']}"
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url, headers=_asset_headers(), timeout=10)
        return r.text

    if msi_zip and msi_sig:
        sig_text = await fetch_sig(msi_sig)
        platforms["windows-x86_64"] = {
            "signature": sig_text,
            "url": f"https://api.labor-ai.org/desktop/download/{version}?platform=windows",
        }

    if mac_tar and mac_sig:
        sig_text = await fetch_sig(mac_sig)
        platforms["darwin-aarch64"] = {
            "signature": sig_text,
            "url": f"https://api.labor-ai.org/desktop/download/{version}?platform=mac",
        }

    if not platforms:
        raise HTTPException(status_code=404, detail="No update assets in latest release")

    return {
        "version": version,
        "notes": release.get("body", ""),
        "pub_date": release["published_at"],
        "platforms": platforms,
    }


@router.get("/download/{version}")
async def download_update(version: str, platform: str = "windows"):
    release, msi_zip, msi_sig, mac_tar, mac_sig = await _get_latest_release_data()
    if release["tag_name"].lstrip("v") != version:
        raise HTTPException(status_code=404, detail="Version not found")

    asset = mac_tar if platform == "mac" else msi_zip

    if not asset:
        raise HTTPException(status_code=404, detail=f"No {platform} asset in release")

    asset_api_url = f"https://api.github.com/repos/ysompo/journal-club/releases/assets/{asset['id']}"

    async def stream_from_github():
        async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
            async with client.stream("GET", asset_api_url, headers=_asset_headers()) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    return StreamingResponse(
        stream_from_github(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{asset["name"]}"',
            "Content-Length": str(asset["size"]),
        },
    )
