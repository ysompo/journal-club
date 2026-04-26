from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite, uuid
from datetime import datetime, timezone, timedelta

from database import get_db
from routers.users import get_current_user

router = APIRouter(prefix="/queue", tags=["queue"])

CLAIM_TIMEOUT_SECONDS = 300  # 5 min — auto-release stale claims
MAX_RETRIES = 1


class QueueRequest(BaseModel):
    input: str


class ClaimRequest(BaseModel):
    device_id: str


class DoneRequest(BaseModel):
    article_id: str


class FailedRequest(BaseModel):
    error: str
    error_step: str = ""
    publisher: str = ""
    log_content: str = ""


@router.post("/", status_code=201)
async def add_to_queue(
    req: QueueRequest,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO queue (id, user_id, input, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (item_id, user["id"], req.input, "queued", now, now),
    )
    await db.commit()
    return {"id": item_id, "input": req.input, "status": "queued", "created_at": now}


@router.get("/")
async def list_queue(
    status: str | None = None,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    # Release stale claims on every poll so crashed sidecars don't block forever.
    stale_before = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TIMEOUT_SECONDS)).isoformat()
    await db.execute(
        "UPDATE queue SET status='queued', claimed_by=NULL, claimed_at=NULL "
        "WHERE user_id=? AND status='claimed' AND claimed_at<?",
        (user["id"], stale_before),
    )
    await db.commit()

    if status:
        async with db.execute(
            "SELECT * FROM queue WHERE user_id=? AND status=? ORDER BY created_at ASC",
            (user["id"], status),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT * FROM queue WHERE user_id=? ORDER BY created_at ASC",
            (user["id"],),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/{item_id}/claim")
async def claim_item(
    item_id: str,
    req: ClaimRequest,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Desktop claims a specific queued item before starting sidecar."""
    now = datetime.now(timezone.utc).isoformat()

    # Release stale claims first
    stale_before = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TIMEOUT_SECONDS)).isoformat()
    await db.execute(
        "UPDATE queue SET status='queued', claimed_by=NULL, claimed_at=NULL "
        "WHERE user_id=? AND status='claimed' AND claimed_at<?",
        (user["id"], stale_before),
    )

    async with db.execute(
        "SELECT * FROM queue WHERE id=? AND user_id=? AND status='queued'",
        (item_id, user["id"]),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="Item not available for claiming")

    await db.execute(
        "UPDATE queue SET status='claimed', claimed_by=?, claimed_at=?, updated_at=? WHERE id=?",
        (req.device_id, now, now, item_id),
    )
    await db.commit()
    return dict(row)


@router.post("/{item_id}/done")
async def mark_done(
    item_id: str,
    req: DoneRequest,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE queue SET status='done', updated_at=? WHERE id=? AND user_id=?",
        (now, item_id, user["id"]),
    )
    await db.commit()
    return {"ok": True}


@router.post("/{item_id}/failed")
async def mark_failed(
    item_id: str,
    req: FailedRequest,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    now = datetime.now(timezone.utc).isoformat()
    async with db.execute(
        "SELECT retry_count FROM queue WHERE id=? AND user_id=?", (item_id, user["id"])
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Queue item not found")

    new_count = (row["retry_count"] or 0) + 1
    final_status = "failed" if new_count >= MAX_RETRIES else "queued"

    await db.execute(
        "UPDATE queue SET status=?, error=?, retry_count=?, updated_at=? WHERE id=? AND user_id=?",
        (final_status, req.error, new_count, now, item_id, user["id"]),
    )
    failure_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO download_failures (id, queue_item_id, user_id, error_step, error_message, publisher, log_content, occurred_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (failure_id, item_id, user["id"], req.error_step, req.error, req.publisher, req.log_content, now),
    )
    await db.commit()
    return {"ok": True, "retry_count": new_count}


@router.post("/{item_id}/retry")
async def retry_item(
    item_id: str,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE queue SET status='queued', claimed_by=NULL, claimed_at=NULL, error=NULL, updated_at=? "
        "WHERE id=? AND user_id=?",
        (now, item_id, user["id"]),
    )
    await db.commit()
    return {"ok": True}


@router.delete("/active")
async def clear_active(
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete ALL queue items for this user (called on desktop restart — full wipe)."""
    await db.execute("DELETE FROM queue WHERE user_id=?", (user["id"],))
    await db.commit()
    return {"ok": True}


@router.delete("/{item_id}")
async def delete_item(
    item_id: str,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute("DELETE FROM queue WHERE id=? AND user_id=?", (item_id, user["id"]))
    await db.commit()
    return {"ok": True}


@router.post("/{item_id}/report")
async def report_failure(
    item_id: str,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Email a failure report to the admin."""
    import resend
    from config import RESEND_API_KEY, RESEND_FROM, ADMIN_EMAIL

    async with db.execute(
        "SELECT q.input, q.error, q.retry_count, df.error_step, df.publisher, df.log_content "
        "FROM queue q LEFT JOIN download_failures df ON df.queue_item_id=q.id "
        "WHERE q.id=? AND q.user_id=? ORDER BY df.occurred_at DESC LIMIT 1",
        (item_id, user["id"]),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Queue item not found")

    resend.api_key = RESEND_API_KEY
    log_section = ""
    log_content = row["log_content"] or ""
    if log_content:
        # Truncate very long logs to keep email under Resend's 40KB limit
        if len(log_content) > 30000:
            log_content = log_content[-30000:]
            log_section = f"\n\n── Full log (last 30KB) ──────────────────────\n{log_content}\n"
        else:
            log_section = f"\n\n── Full log ──────────────────────────────────\n{log_content}\n"
    body = (
        f"Download failure report\n\n"
        f"User: {user['huji_username']}\n"
        f"Input: {row['input']}\n"
        f"Error: {row['error']}\n"
        f"Step: {row['error_step'] or 'unknown'}\n"
        f"Publisher: {row['publisher'] or 'unknown'}\n"
        f"Retries: {row['retry_count']}\n"
        f"{log_section}"
    )
    resend.Emails.send({
        "from": RESEND_FROM,
        "to": [ADMIN_EMAIL],
        "subject": f"[JC] Download failure: {(row['input'] or '')[:60]}",
        "text": body,
    })

    await db.execute(
        "UPDATE download_failures SET reported=1 WHERE queue_item_id=?", (item_id,)
    )
    await db.commit()
    return {"ok": True}
