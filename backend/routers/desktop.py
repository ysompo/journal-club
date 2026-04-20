import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/desktop", tags=["desktop"])

_GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/ysompo/journal-club/releases/latest"
)
_GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


@router.get("/latest")
async def get_latest_release():
    async with httpx.AsyncClient() as client:
        resp = await client.get(_GITHUB_RELEASES_URL, headers=_GITHUB_HEADERS, timeout=10)

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub API unavailable")

    release = resp.json()
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}

    zip_url = next(
        (v for k, v in assets.items() if k.endswith(".msi.zip") and not k.endswith(".sig")),
        None,
    )
    sig_url = next(
        (v for k, v in assets.items() if k.endswith(".msi.zip.sig")),
        None,
    )

    if not zip_url or not sig_url:
        raise HTTPException(status_code=404, detail="No MSI assets in latest release")

    async with httpx.AsyncClient() as client:
        sig_resp = await client.get(sig_url, timeout=10)

    return {
        "version": release["tag_name"].lstrip("v"),
        "notes": release.get("body", ""),
        "pub_date": release["published_at"],
        "platforms": {
            "windows-x86_64": {
                "signature": sig_resp.text,
                "url": zip_url,
            }
        },
    }
