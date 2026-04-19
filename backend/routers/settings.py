from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
import aiosqlite, json

from database import get_db
from routers.users import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    theme: str | None = None
    font_size: str | None = None
    email_addresses: list[str] | None = None

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str | None) -> str | None:
        if v is not None and v not in ("light", "dark", "system"):
            raise ValueError("theme must be light, dark, or system")
        return v

    @field_validator("font_size")
    @classmethod
    def validate_font_size(cls, v: str | None) -> str | None:
        if v is not None and v not in ("small", "medium", "large"):
            raise ValueError("font_size must be small, medium, or large")
        return v

    @field_validator("email_addresses")
    @classmethod
    def validate_emails(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) > 3:
            raise ValueError("max 3 email addresses")
        return v


@router.get("/")
async def get_settings(
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT * FROM settings WHERE user_id=?", (user["id"],)) as cur:
        row = await cur.fetchone()
    if not row:
        return {"theme": "system", "font_size": "medium", "email_addresses": []}
    return {
        "theme": row["theme"] or "system",
        "font_size": row["font_size"] or "medium",
        "email_addresses": json.loads(row["email_addresses"] or "[]"),
    }


@router.patch("/")
async def update_settings(
    req: SettingsUpdate,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT * FROM settings WHERE user_id=?", (user["id"],)) as cur:
        row = await cur.fetchone()
    current = {
        "theme": (row["theme"] if row else None) or "system",
        "font_size": (row["font_size"] if row else None) or "medium",
        "email_addresses": json.loads(row["email_addresses"] or "[]") if row else [],
    }
    if req.theme is not None:
        current["theme"] = req.theme
    if req.font_size is not None:
        current["font_size"] = req.font_size
    if req.email_addresses is not None:
        current["email_addresses"] = req.email_addresses

    await db.execute(
        "INSERT OR REPLACE INTO settings (user_id, theme, font_size, email_addresses) VALUES (?,?,?,?)",
        (user["id"], current["theme"], current["font_size"], json.dumps(current["email_addresses"])),
    )
    await db.commit()
    return current
