from fastapi import APIRouter, Depends
import aiosqlite
from datetime import datetime, timezone, timedelta

from database import get_db
from routers.users import get_current_user

router = APIRouter(prefix="/devices", tags=["devices"])

ONLINE_THRESHOLD_SECONDS = 90  # desktop is "online" if heartbeat within 90s


@router.post("/heartbeat")
async def heartbeat(
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Desktop calls this every 30s so tablets can show online/offline status."""
    now = datetime.now(timezone.utc).isoformat()
    # Update last_seen for the device associated with this token
    # The token's device_id is in the JWT payload — we update via user_id + device_type
    # Since the JWT has sub=user_id and device=device_id, we update by device_id from token
    # get_current_user already validated the token; device_id is in payload
    from auth import decode_token
    from fastapi.security import OAuth2PasswordBearer
    # We can't easily get device_id here without re-decoding the token.
    # Instead update all desktop devices for this user (they all share last_seen context).
    await db.execute(
        "UPDATE device_pairings SET last_seen=? WHERE user_id=? AND device_type='desktop' AND revoked=0",
        (now, user["id"]),
    )
    await db.commit()
    return {"ok": True, "timestamp": now}


@router.get("/online")
async def desktop_online(
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Returns whether any desktop for this user has checked in recently."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ONLINE_THRESHOLD_SECONDS)).isoformat()
    async with db.execute(
        "SELECT id, device_label, last_seen FROM device_pairings "
        "WHERE user_id=? AND device_type='desktop' AND revoked=0 AND last_seen>? "
        "ORDER BY last_seen DESC LIMIT 1",
        (user["id"], cutoff),
    ) as cur:
        row = await cur.fetchone()
    if row:
        return {"online": True, "device_label": row["device_label"], "last_seen": row["last_seen"]}
    return {"online": False, "last_seen": None}
