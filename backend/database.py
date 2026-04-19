import aiosqlite
from config import DB_PATH

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                huji_username TEXT UNIQUE NOT NULL,
                display_name TEXT,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active TEXT,
                storage_bytes_used INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS device_pairings (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                device_label TEXT NOT NULL,
                device_type TEXT NOT NULL CHECK(device_type IN ('desktop', 'tablet')),
                last_seen TEXT,
                revoked INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS qr_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                expires_at TEXT NOT NULL,
                used INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                authors TEXT NOT NULL,      -- JSON array
                journal TEXT,
                year INTEGER,
                doi TEXT,
                url TEXT NOT NULL,
                abstract TEXT,
                pmid TEXT,
                volume TEXT,
                issue TEXT,
                pages TEXT,
                pub_date TEXT,
                keywords TEXT DEFAULT '[]', -- JSON array
                mesh_terms TEXT DEFAULT '[]',
                added_at TEXT NOT NULL,
                pdf_size_bytes INTEGER,
                pdf_on_server INTEGER DEFAULT 0,
                pdf_path TEXT
            );

            CREATE TABLE IF NOT EXISTS selected_articles (
                user_id TEXT NOT NULL REFERENCES users(id),
                article_id TEXT NOT NULL REFERENCES articles(id),
                starred_at TEXT NOT NULL,
                tags TEXT DEFAULT '[]',     -- JSON array
                PRIMARY KEY (user_id, article_id)
            );

            CREATE TABLE IF NOT EXISTS queue (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                input TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK(status IN ('queued','claimed','downloading','done','failed')),
                claimed_by TEXT,
                claimed_at TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS download_failures (
                id TEXT PRIMARY KEY,
                queue_item_id TEXT REFERENCES queue(id),
                user_id TEXT NOT NULL REFERENCES users(id),
                article_id TEXT,
                error_step TEXT,
                error_message TEXT,
                publisher TEXT,
                occurred_at TEXT NOT NULL,
                reported INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                user_id TEXT PRIMARY KEY REFERENCES users(id),
                theme TEXT DEFAULT 'system',
                font_size TEXT DEFAULT 'medium',
                email_addresses TEXT DEFAULT '[]'  -- JSON array, max 3
            );

            CREATE TABLE IF NOT EXISTS invites (
                id TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                created_by TEXT NOT NULL REFERENCES users(id),
                used_by TEXT REFERENCES users(id),
                used_at TEXT,
                created_at TEXT NOT NULL,
                note TEXT
            );
        """)
        await db.commit()
