import os

APP_VERSION = "0.1.0"

SECRET_KEY = os.environ.get("JC_SECRET_KEY", "dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days for tablet sessions
QR_TOKEN_EXPIRE_MINUTES = 5                  # short-lived pairing token

DB_PATH = os.environ.get("JC_DB_PATH", "journal_club_app.db")
PDF_DIR = os.environ.get("JC_PDF_DIR", "pdf_storage")
STORAGE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2GB per user

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
REQUIRE_INVITE_CODE = os.environ.get("JC_REQUIRE_INVITE", "false").lower() == "true"
RESEND_FROM = "Journal Club <noreply@yourdomain.com>"
ADMIN_EMAIL = "ysompo@gmail.com"

FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "https://journal.yourdomain.com",  # update with real subdomain
]
