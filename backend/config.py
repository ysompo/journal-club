import os

APP_VERSION = "0.1.0"

SECRET_KEY = os.environ.get("JC_SECRET_KEY", "dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days for tablet sessions
QR_TOKEN_EXPIRE_MINUTES = 5                  # short-lived pairing token

DB_PATH = os.environ.get("JC_DB_PATH", "journal_club_app.db")
PDF_DIR = os.environ.get("JC_PDF_DIR", "pdf_storage")  # local fallback only; R2 used in prod
# Per-user: ~50 PDFs @ ~1.5MB each. Auto-prune-oldest kicks in beyond this.
STORAGE_LIMIT_BYTES = int(os.environ.get("JC_STORAGE_LIMIT_BYTES", str(75 * 1024 * 1024)))
# Global: stay safely under R2 free tier (10GB). Refuse uploads beyond this.
GLOBAL_STORAGE_LIMIT_BYTES = int(os.environ.get("JC_GLOBAL_STORAGE_LIMIT_BYTES", str(8 * 1024 * 1024 * 1024)))

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
REQUIRE_INVITE_CODE = os.environ.get("JC_REQUIRE_INVITE", "false").lower() == "true"
RESEND_FROM = os.environ.get("RESEND_FROM", "Journal Club <noreply@example.com>")
ADMIN_EMAIL = "ysompo@gmail.com"

FRONTEND_ORIGINS = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
