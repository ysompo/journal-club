from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
import aiosqlite, uuid, os, json, shutil, base64, re, httpx
from datetime import datetime, timezone

from database import get_db
from routers.users import get_current_user
from config import PDF_DIR, STORAGE_LIMIT_BYTES, RESEND_API_KEY, RESEND_FROM

router = APIRouter(prefix="/articles", tags=["articles"])


class ArticleCreate(BaseModel):
    title: str
    authors: list[str]
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    url: str
    abstract: str | None = None
    pmid: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    pub_date: str | None = None
    keywords: list[str] = []
    mesh_terms: list[str] = []


class TagsUpdate(BaseModel):
    tags: list[str]


class EmailRequest(BaseModel):
    article_ids: list[str]


@router.get("/")
async def list_articles(
    q: str | None = None,
    tag: str | None = None,
    selected_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    base = """
        SELECT a.*,
               sa.tags      AS _sa_tags,
               sa.starred_at AS _sa_starred_at
        FROM articles a
        LEFT JOIN selected_articles sa ON sa.article_id=a.id AND sa.user_id=?
        WHERE a.user_id=?
    """
    params: list = [user["id"], user["id"]]

    if selected_only:
        base += " AND sa.article_id IS NOT NULL"
    if q:
        base += " AND (a.title LIKE ? OR a.abstract LIKE ? OR a.keywords LIKE ? OR a.mesh_terms LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
    if tag:
        base += " AND sa.tags LIKE ?"
        params.append(f'%"{tag}"%')

    count_query = f"SELECT COUNT(*) AS n FROM ({base})"
    async with db.execute(count_query, params) as cur:
        count_row = await cur.fetchone()
    total = count_row["n"] if count_row else 0

    base += " ORDER BY a.added_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    async with db.execute(base, params) as cur:
        rows = await cur.fetchall()

    items = []
    for r in rows:
        row = dict(r)
        row["authors"] = json.loads(row.get("authors") or "[]")
        row["keywords"] = json.loads(row.get("keywords") or "[]")
        row["mesh_terms"] = json.loads(row.get("mesh_terms") or "[]")
        sa_tags_raw = row.pop("_sa_tags", None)
        row.pop("_sa_starred_at", None)
        row["tags"] = json.loads(sa_tags_raw) if sa_tags_raw else []
        row["is_selected"] = sa_tags_raw is not None
        items.append(row)

    return {"items": items, "total": total}


@router.post("/", status_code=201)
async def create_article(
    article: ArticleCreate,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    article_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO articles
           (id, user_id, title, authors, journal, year, doi, url, abstract, pmid,
            volume, issue, pages, pub_date, keywords, mesh_terms, added_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (article_id, user["id"], article.title, json.dumps(article.authors),
         article.journal, article.year, article.doi, article.url,
         article.abstract, article.pmid, article.volume, article.issue,
         article.pages, article.pub_date, json.dumps(article.keywords),
         json.dumps(article.mesh_terms), now),
    )
    await db.commit()
    async with db.execute("SELECT * FROM articles WHERE id=?", (article_id,)) as cur:
        row = await cur.fetchone()
    result = dict(row)
    result["authors"] = json.loads(result.get("authors") or "[]")
    result["keywords"] = json.loads(result.get("keywords") or "[]")
    result["mesh_terms"] = json.loads(result.get("mesh_terms") or "[]")
    result["tags"] = []
    result["is_selected"] = False
    return result


# ── Tags autocomplete ─────────────────────────────────────────────────────────

@router.get("/tags")
async def get_tags(
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT tags FROM selected_articles WHERE user_id=?", (user["id"],)
    ) as cur:
        rows = await cur.fetchall()
    all_tags: set[str] = set()
    for row in rows:
        all_tags.update(json.loads(row["tags"] or "[]"))
    return sorted(all_tags)


# ── Email to self ─────────────────────────────────────────────────────────────

@router.post("/email")
async def email_articles(
    req: EmailRequest,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="Email not configured on server")
    if len(req.article_ids) == 0:
        raise HTTPException(status_code=400, detail="No articles selected")
    if len(req.article_ids) > 10:
        raise HTTPException(status_code=400, detail="Max 10 articles per email")

    async with db.execute(
        "SELECT email_addresses FROM settings WHERE user_id=?", (user["id"],)
    ) as cur:
        row = await cur.fetchone()
    addresses = json.loads(row["email_addresses"] or "[]") if row else []
    if not addresses:
        raise HTTPException(status_code=400, detail="No email addresses configured in settings")

    attachments = []
    titles = []
    for article_id in req.article_ids:
        async with db.execute(
            "SELECT title, pdf_path, pdf_on_server FROM articles WHERE id=? AND user_id=?",
            (article_id, user["id"]),
        ) as cur:
            article = await cur.fetchone()
        if not article or not article["pdf_on_server"] or not article["pdf_path"]:
            raise HTTPException(status_code=404, detail=f"PDF not available for article {article_id}")
        with open(article["pdf_path"], "rb") as f:
            content = base64.b64encode(f.read()).decode()
        safe_name = re.sub(r'[^\w\s-]', '', article["title"])[:60].strip().replace(" ", "_") + ".pdf"
        attachments.append({"filename": safe_name, "content": content})
        titles.append(article["title"])

    subject = f"Journal Club: {len(titles)} article{'s' if len(titles) > 1 else ''}"
    body = "Your requested articles:\n\n" + "\n".join(f"• {t}" for t in titles)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": RESEND_FROM,
                "to": addresses,
                "subject": subject,
                "text": body,
                "attachments": attachments,
            },
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Email service error: {resp.text[:200]}")

    return {"ok": True, "sent_to": addresses}


# ── PDF upload / download ─────────────────────────────────────────────────────

@router.post("/{article_id}/pdf")
async def upload_pdf(
    article_id: str,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT id FROM articles WHERE id=? AND user_id=?", (article_id, user["id"])
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Article not found")

    user_dir = os.path.join(PDF_DIR, user["id"])
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, f"{article_id}.pdf")

    content = await file.read()
    size = len(content)

    if user["storage_bytes_used"] + size > STORAGE_LIMIT_BYTES:
        await _prune_oldest(user["id"], size, db)

    with open(pdf_path, "wb") as f:
        f.write(content)

    await db.execute(
        "UPDATE articles SET pdf_size_bytes=?, pdf_on_server=1, pdf_path=? WHERE id=?",
        (size, pdf_path, article_id),
    )
    await db.execute(
        "UPDATE users SET storage_bytes_used=storage_bytes_used+? WHERE id=?",
        (size, user["id"]),
    )
    await db.commit()
    return {"size": size}


@router.get("/{article_id}/pdf")
async def download_pdf(
    article_id: str,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT pdf_path, pdf_on_server FROM articles WHERE id=? AND user_id=?",
        (article_id, user["id"]),
    ) as cur:
        row = await cur.fetchone()
    if not row or not row["pdf_on_server"]:
        raise HTTPException(status_code=404, detail="PDF not on server")
    return FileResponse(row["pdf_path"], media_type="application/pdf")


# ── Select / star ─────────────────────────────────────────────────────────────

@router.post("/{article_id}/select", status_code=201)
async def select_article(
    article_id: str,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT id FROM articles WHERE id=? AND user_id=?", (article_id, user["id"])
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Article not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR IGNORE INTO selected_articles (user_id, article_id, starred_at, tags) VALUES (?,?,?,?)",
        (user["id"], article_id, now, "[]"),
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{article_id}/select")
async def deselect_article(
    article_id: str,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute(
        "DELETE FROM selected_articles WHERE user_id=? AND article_id=?",
        (user["id"], article_id),
    )
    await db.commit()
    return {"ok": True}


@router.put("/{article_id}/tags")
async def update_tags(
    article_id: str,
    req: TagsUpdate,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT 1 FROM selected_articles WHERE user_id=? AND article_id=?",
        (user["id"], article_id),
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Article not starred")
    await db.execute(
        "UPDATE selected_articles SET tags=? WHERE user_id=? AND article_id=?",
        (json.dumps(req.tags), user["id"], article_id),
    )
    await db.commit()
    return {"tags": req.tags}


# ── Delete article ────────────────────────────────────────────────────────────

@router.delete("/{article_id}")
async def delete_article(
    article_id: str,
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT pdf_path, pdf_size_bytes FROM articles WHERE id=? AND user_id=?",
        (article_id, user["id"]),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")

    if row["pdf_path"] and os.path.exists(row["pdf_path"]):
        os.remove(row["pdf_path"])
        await db.execute(
            "UPDATE users SET storage_bytes_used=MAX(0,storage_bytes_used-?) WHERE id=?",
            (row["pdf_size_bytes"] or 0, user["id"]),
        )

    await db.execute("DELETE FROM selected_articles WHERE article_id=? AND user_id=?", (article_id, user["id"]))
    await db.execute("DELETE FROM articles WHERE id=? AND user_id=?", (article_id, user["id"]))
    await db.commit()
    return {"ok": True}


async def _prune_oldest(user_id: str, needed_bytes: int, db: aiosqlite.Connection):
    async with db.execute(
        "SELECT id, pdf_path, pdf_size_bytes FROM articles WHERE user_id=? AND pdf_on_server=1 ORDER BY added_at ASC",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
    for row in rows:
        if not row["pdf_path"] or not os.path.exists(row["pdf_path"]):
            continue
        os.remove(row["pdf_path"])
        freed = row["pdf_size_bytes"] or 0
        await db.execute(
            "UPDATE articles SET pdf_on_server=0, pdf_path=NULL WHERE id=?", (row["id"],)
        )
        await db.execute(
            "UPDATE users SET storage_bytes_used=MAX(0,storage_bytes_used-?) WHERE id=?",
            (freed, user_id),
        )
        needed_bytes -= freed
        if needed_bytes <= 0:
            break
