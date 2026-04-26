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
    asset_list = release.get("assets", [])
    assets_by_name = {a["name"]: a for a in asset_list}
    msi_zip = next((a for n, a in assets_by_name.items() if n.endswith(".msi.zip") and not n.endswith(".sig")), None)
    sig_asset = next((a for n, a in assets_by_name.items() if n.endswith(".msi.zip.sig")), None)
    if not msi_zip or not sig_asset:
        raise HTTPException(status_code=404, detail="No MSI assets in latest release")
    return release, msi_zip, sig_asset


@router.get("/latest")
async def get_latest_release():
    release, msi_zip, sig_asset = await _get_latest_release_data()

    sig_api_url = f"https://api.github.com/repos/ysompo/journal-club/releases/assets/{sig_asset['id']}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        sig_resp = await client.get(sig_api_url, headers=_asset_headers(), timeout=10)

    version = release["tag_name"].lstrip("v")
    return {
        "version": version,
        "notes": release.get("body", ""),
        "pub_date": release["published_at"],
        "platforms": {
            "windows-x86_64": {
                "signature": sig_resp.text,
                "url": f"https://api.labor-ai.org/desktop/download/{version}",
            }
        },
    }


@router.get("/download/{version}")
async def download_update(version: str):
    release, msi_zip, _ = await _get_latest_release_data()
    if release["tag_name"].lstrip("v") != version:
        raise HTTPException(status_code=404, detail="Version not found")

    asset_api_url = f"https://api.github.com/repos/ysompo/journal-club/releases/assets/{msi_zip['id']}"

    async def stream_from_github():
        async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
            async with client.stream("GET", asset_api_url, headers=_asset_headers()) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    filename = msi_zip["name"]
    return StreamingResponse(
        stream_from_github(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(msi_zip["size"]),
        },
    )
