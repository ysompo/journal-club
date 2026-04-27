"""PDF storage abstraction. Backed by Cloudflare R2 in production, local
filesystem in dev. Switch via env: set R2_BUCKET + R2_ENDPOINT + R2_ACCESS_KEY_ID
+ R2_SECRET_ACCESS_KEY to enable R2; otherwise falls back to PDF_DIR on disk.

The `key` is always `{user_id}/{article_id}.pdf` and is stored in
`articles.pdf_path` so the same column works for both modes.
"""
from __future__ import annotations
import os
from typing import Optional

R2_BUCKET = os.environ.get("R2_BUCKET", "")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
LOCAL_PDF_DIR = os.environ.get("JC_PDF_DIR", "pdf_storage")

USE_R2 = bool(R2_BUCKET and R2_ENDPOINT and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        import boto3
        from botocore.config import Config
        _s3 = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _s3


def storage_key(user_id: str, article_id: str) -> str:
    return f"{user_id}/{article_id}.pdf"


def write(key: str, data: bytes) -> None:
    if USE_R2:
        _client().put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType="application/pdf")
    else:
        path = os.path.join(LOCAL_PDF_DIR, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def read(key: str) -> bytes:
    if USE_R2:
        resp = _client().get_object(Bucket=R2_BUCKET, Key=key)
        return resp["Body"].read()
    path = os.path.join(LOCAL_PDF_DIR, key) if not os.path.isabs(key) else key
    with open(path, "rb") as f:
        return f.read()


def delete(key: str) -> None:
    if USE_R2:
        try:
            _client().delete_object(Bucket=R2_BUCKET, Key=key)
        except Exception:
            pass
        return
    path = os.path.join(LOCAL_PDF_DIR, key) if not os.path.isabs(key) else key
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def exists(key: str) -> bool:
    if USE_R2:
        try:
            _client().head_object(Bucket=R2_BUCKET, Key=key)
            return True
        except Exception:
            return False
    path = os.path.join(LOCAL_PDF_DIR, key) if not os.path.isabs(key) else key
    return os.path.exists(path)
