from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, QR_TOKEN_EXPIRE_MINUTES
import secrets

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))

def create_access_token(user_id: str, device_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "device": device_id, "exp": expire},
        SECRET_KEY, algorithm=ALGORITHM,
    )

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

def generate_qr_token() -> str:
    return secrets.token_urlsafe(32)

def qr_token_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=QR_TOKEN_EXPIRE_MINUTES)).isoformat()
