import aiosqlite
from config import DB_PATH

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

JOURNALS_SEED = [
    # General Medicine
    ("nejm", "New England Journal of Medicine", "NEJM", "0028-4793", "general"),
    ("lancet", "The Lancet", "Lancet", "0140-6736", "general"),
    ("jama", "JAMA", "JAMA", "0098-7484", "general"),
    ("bmj", "BMJ", "BMJ", "0959-8138", "general"),
    ("ann-intern-med", "Annals of Internal Medicine", "Ann Intern Med", "0003-4819", "general"),
    ("nature-med", "Nature Medicine", "Nat Med", "1078-8956", "general"),
    ("jama-intern-med", "JAMA Internal Medicine", "JAMA Intern Med", "2168-6106", "general"),
    ("plos-med", "PLOS Medicine", "PLoS Med", "1549-1676", "general"),
    ("am-j-med", "The American Journal of Medicine", "Am J Med", "1555-7162", "general"),
    ("j-gen-intern-med", "Journal of General Internal Medicine", "J Gen Intern Med", "0884-8734", "general"),
    # OB/GYN
    ("ajog", "American Journal of Obstetrics and Gynecology", "AJOG", "0002-9378", "obgyn"),
    ("obs-gyn", "Obstetrics & Gynecology", "Obstet Gynecol", "0029-7844", "obgyn"),
    ("bjog", "BJOG: An International Journal of Obstetrics and Gynaecology", "BJOG", "1470-0328", "obgyn"),
    ("fertil-steril", "Fertility and Sterility", "Fertil Steril", "0015-0282", "obgyn"),
    ("hum-reprod", "Human Reproduction", "Hum Reprod", "0268-1161", "obgyn"),
    ("hum-reprod-update", "Human Reproduction Update", "Hum Reprod Update", "1355-4786", "obgyn"),
    ("gynecol-oncol", "Gynecologic Oncology", "Gynecol Oncol", "0090-8258", "obgyn"),
    ("ajog-mfm", "American Journal of Obstetrics & Gynecology MFM", "AJOG MFM", "2589-9333", "obgyn"),
    ("j-matern-fetal", "Journal of Maternal-Fetal & Neonatal Medicine", "J Matern Fetal Neonatal Med", "1476-7058", "obgyn"),
    ("ultrasound-og", "Ultrasound in Obstetrics and Gynecology", "Ultrasound Obstet Gynecol", "0960-7692", "obgyn"),
    ("prenat-diagn", "Prenatal Diagnosis", "Prenat Diagn", "0197-3851", "obgyn"),
    ("eur-j-obstet", "European Journal of Obstetrics & Gynecology and Reproductive Biology", "Eur J Obstet Gynecol Reprod Biol", "0301-2115", "obgyn"),
    ("int-j-gynecol", "International Journal of Gynecology & Obstetrics", "Int J Gynaecol Obstet", "0020-7292", "obgyn"),
    ("acta-obstet", "Acta Obstetricia et Gynecologica Scandinavica", "Acta Obstet Gynecol Scand", "0001-6349", "obgyn"),
    ("arch-gynecol", "Archives of Gynecology and Obstetrics", "Arch Gynecol Obstet", "0932-0067", "obgyn"),
    ("placenta", "Placenta", "Placenta", "0143-4004", "obgyn"),
    ("j-perinatol", "Journal of Perinatology", "J Perinatol", "0743-8346", "obgyn"),
    ("j-minim-invasive-gyn", "Journal of Minimally Invasive Gynecology", "J Minim Invasive Gynecol", "1553-4650", "obgyn"),
    ("reprod-sci", "Reproductive Sciences", "Reprod Sci", "1933-7191", "obgyn"),
    ("menopause", "Menopause", "Menopause", "1072-3714", "obgyn"),
    ("gynecol-endocrinol", "Gynecological Endocrinology", "Gynecol Endocrinol", "0951-3590", "obgyn"),
    ("j-gynecol-oncol", "Journal of Gynecologic Oncology", "J Gynecol Oncol", "2005-0380", "obgyn"),
    ("int-j-gynecol-cancer", "International Journal of Gynecological Cancer", "Int J Gynecol Cancer", "1048-891X", "obgyn"),
    ("reprod-biomed-online", "Reproductive BioMedicine Online", "Reprod Biomed Online", "1472-6483", "obgyn"),
    ("j-reprod-med", "Journal of Reproductive Medicine", "J Reprod Med", "0024-7758", "obgyn"),
]

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
                log_content TEXT,
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

            CREATE TABLE IF NOT EXISTS journals (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                abbreviation TEXT NOT NULL,
                issn TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('general','obgyn','custom'))
            );

            CREATE TABLE IF NOT EXISTS journal_follows (
                user_id TEXT NOT NULL REFERENCES users(id),
                journal_id TEXT NOT NULL REFERENCES journals(id),
                followed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, journal_id)
            );

            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                pmid TEXT,
                doi TEXT,
                title TEXT NOT NULL,
                authors TEXT NOT NULL,
                journal TEXT,
                pub_date TEXT,
                abstract TEXT,
                url TEXT,
                queued_at TEXT NOT NULL
            );
        """)
        await db.commit()

        # Seed journals if empty
        async with db.execute("SELECT COUNT(*) FROM journals") as cur:
            count = (await cur.fetchone())[0]
        if count == 0:
            await db.executemany(
                "INSERT OR IGNORE INTO journals (id, full_name, abbreviation, issn, category) VALUES (?,?,?,?,?)",
                JOURNALS_SEED,
            )
            await db.commit()
