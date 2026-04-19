from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite, uuid, secrets
from datetime import datetime, timezone

from database import get_db
from routers.users import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/users")
async def list_users(
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("""
        SELECT u.id, u.huji_username, u.display_name, u.created_at, u.last_active,
               u.storage_bytes_used, u.is_admin,
               COUNT(DISTINCT a.id)  AS article_count,
               COUNT(DISTINCT dp.id) AS device_count
        FROM users u
        LEFT JOIN articles a  ON a.user_id  = u.id
        LEFT JOIN device_pairings dp ON dp.user_id = u.id AND dp.revoked = 0
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: str,
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    new_val = 0 if row["is_admin"] else 1
    await db.execute("UPDATE users SET is_admin=? WHERE id=?", (new_val, user_id))
    await db.commit()
    return {"is_admin": bool(new_val)}


@router.get("/reports")
async def list_reports(
    resolved: bool = False,
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("""
        SELECT df.id, df.queue_item_id, df.error_step, df.error_message, df.publisher,
               df.occurred_at, df.reported,
               u.huji_username,
               q.input AS queue_input
        FROM download_failures df
        JOIN  users u ON u.id = df.user_id
        LEFT JOIN queue q ON q.id = df.queue_item_id
        WHERE df.reported = ?
        ORDER BY df.occurred_at DESC
        LIMIT 200
    """, (1 if resolved else 0,)) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/reports/{failure_id}/resolve")
async def resolve_report(
    failure_id: str,
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute("UPDATE download_failures SET reported=1 WHERE id=?", (failure_id,))
    await db.commit()
    return {"ok": True}


# ── Invite codes ─────────────────────────────────────────────────────────────

class CreateInviteRequest(BaseModel):
    note: str | None = None


@router.post("/invites", status_code=201)
async def create_invite(
    req: CreateInviteRequest,
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    code = secrets.token_hex(4).upper()  # e.g. "A3B7F92D"
    invite_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO invites (id, code, created_by, created_at, note) VALUES (?,?,?,?,?)",
        (invite_id, code, user["id"], now, req.note),
    )
    await db.commit()
    return {"id": invite_id, "code": code, "note": req.note, "created_at": now}


@router.get("/invites")
async def list_invites(
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("""
        SELECT i.id, i.code, i.note, i.created_at, i.used_at,
               u.huji_username AS used_by_name
        FROM invites i
        LEFT JOIN users u ON u.id = i.used_by
        ORDER BY i.created_at DESC
    """) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.delete("/invites/{invite_id}")
async def delete_invite(
    invite_id: str,
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute("DELETE FROM invites WHERE id=? AND used_by IS NULL", (invite_id,))
    await db.commit()
    return {"ok": True}


@router.get("/stats")
async def stats(
    user=Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT COUNT(*) AS n FROM users") as cur:
        users_count = (await cur.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) AS n FROM articles") as cur:
        articles_count = (await cur.fetchone())["n"]
    async with db.execute("SELECT SUM(storage_bytes_used) AS n FROM users") as cur:
        storage_used = (await cur.fetchone())["n"] or 0
    async with db.execute("SELECT COUNT(*) AS n FROM queue WHERE status='queued'") as cur:
        queued_count = (await cur.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) AS n FROM download_failures WHERE reported=0") as cur:
        open_reports = (await cur.fetchone())["n"]
    return {
        "users": users_count,
        "articles": articles_count,
        "storage_bytes_used": storage_used,
        "queued_items": queued_count,
        "open_reports": open_reports,
    }
