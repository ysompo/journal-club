from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import aiosqlite, uuid
from datetime import datetime, timezone

from database import get_db
from auth import hash_password, verify_password, create_access_token, decode_token, generate_qr_token, qr_token_expires_at
from config import SECRET_KEY, ALGORITHM, REQUIRE_INVITE_CODE

router = APIRouter(prefix="/users", tags=["users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


class RegisterRequest(BaseModel):
    huji_username: str
    password: str
    display_name: str | None = None
    device_label: str = "desktop"
    invite_code: str | None = None


class LoginRequest(BaseModel):
    huji_username: str
    password: str
    device_label: str = "desktop"


async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    try:
        payload = decode_token(token)
        user_id = payload["sub"]
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    async with db.execute("SELECT * FROM users WHERE id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: aiosqlite.Connection = Depends(get_db)):
    # Invite-code gate
    if REQUIRE_INVITE_CODE:
        if not req.invite_code:
            raise HTTPException(status_code=400, detail="An invite code is required to register")
        async with db.execute(
            "SELECT id FROM invites WHERE code=? AND used_by IS NULL", (req.invite_code,)
        ) as cur:
            invite = await cur.fetchone()
        if not invite:
            raise HTTPException(status_code=400, detail="Invalid or already-used invite code")

    async with db.execute("SELECT id FROM users WHERE huji_username=?", (req.huji_username,)) as cur:
        if await cur.fetchone():
            raise HTTPException(status_code=409, detail="Username already registered")

    user_id = str(uuid.uuid4())
    device_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "INSERT INTO users (id, huji_username, display_name, password_hash, created_at) VALUES (?,?,?,?,?)",
        (user_id, req.huji_username, req.display_name, hash_password(req.password), now),
    )
    await db.execute(
        "INSERT INTO device_pairings (id, user_id, device_label, device_type, last_seen, created_at) VALUES (?,?,?,?,?,?)",
        (device_id, user_id, req.device_label, "desktop", now, now),
    )
    await db.execute("INSERT INTO settings (user_id) VALUES (?)", (user_id,))

    if REQUIRE_INVITE_CODE and req.invite_code:
        await db.execute(
            "UPDATE invites SET used_by=?, used_at=? WHERE code=?",
            (user_id, now, req.invite_code),
        )

    await db.commit()

    token = create_access_token(user_id, device_id)
    return {"access_token": token, "token_type": "bearer", "user_id": user_id}


@router.post("/login")
async def login(req: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM users WHERE huji_username=?", (req.huji_username,)) as cur:
        row = await cur.fetchone()
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    device_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO device_pairings (id, user_id, device_label, device_type, last_seen, created_at) VALUES (?,?,?,?,?,?)",
        (device_id, row["id"], req.device_label, "desktop", now, now),
    )
    await db.execute("UPDATE users SET last_active=? WHERE id=?", (now, row["id"]))
    await db.commit()

    token = create_access_token(row["id"], device_id)
    return {"access_token": token, "token_type": "bearer", "user_id": row["id"]}


@router.post("/qr-token")
async def create_qr_token(user=Depends(get_current_user), db: aiosqlite.Connection = Depends(get_db)):
    token = generate_qr_token()
    expires = qr_token_expires_at()
    await db.execute(
        "INSERT INTO qr_tokens (token, user_id, expires_at) VALUES (?,?,?)",
        (token, user["id"], expires),
    )
    await db.commit()
    return {"qr_token": token, "expires_at": expires}


class PairTabletRequest(BaseModel):
    qr_token: str
    device_label: str = "tablet"

@router.post("/pair-tablet")
async def pair_tablet(req: PairTabletRequest, db: aiosqlite.Connection = Depends(get_db)):
    qr_token = req.qr_token
    device_label = req.device_label
    now = datetime.now(timezone.utc).isoformat()
    async with db.execute(
        "SELECT * FROM qr_tokens WHERE token=? AND used=0 AND expires_at > ?",
        (qr_token, now),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired QR token")

    device_id = str(uuid.uuid4())
    await db.execute("UPDATE qr_tokens SET used=1 WHERE token=?", (qr_token,))
    await db.execute(
        "INSERT INTO device_pairings (id, user_id, device_label, device_type, last_seen, created_at) VALUES (?,?,?,?,?,?)",
        (device_id, row["user_id"], device_label, "tablet", now, now),
    )
    await db.commit()

    token = create_access_token(row["user_id"], device_id)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {k: v for k, v in user.items() if k != "password_hash"}
