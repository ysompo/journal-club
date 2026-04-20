from fastapi import APIRouter, Depends
from pydantic import BaseModel
import aiosqlite, uuid, json
from datetime import datetime, timezone

from database import get_db
from routers.users import get_current_user

router = APIRouter(prefix="/history", tags=["history"])


class HistoryCreate(BaseModel):
    pmid: str | None = None
    doi: str | None = None
    title: str
    authors: list[str]
    journal: str | None = None
    pub_date: str | None = None
    abstract: str | None = None
    url: str | None = None


@router.get("/")
async def list_history(
    limit: int = 50,
    offset: int = 0,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    async with db.execute(
        "SELECT * FROM history WHERE user_id=? ORDER BY queued_at DESC LIMIT ? OFFSET ?",
        (user["id"], limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {**dict(r), "authors": json.loads(r["authors"])}
        for r in rows
    ]


@router.post("/", status_code=201)
async def add_history(req: HistoryCreate, user=Depends(get_current_user), db=Depends(get_db)):
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO history (id, user_id, pmid, doi, title, authors, journal, pub_date, abstract, url, queued_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (item_id, user["id"], req.pmid, req.doi, req.title,
         json.dumps(req.authors), req.journal, req.pub_date, req.abstract, req.url, now),
    )
    await db.commit()
    return {"id": item_id, "queued_at": now}


@router.delete("/{item_id}")
async def delete_history(item_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    await db.execute("DELETE FROM history WHERE id=? AND user_id=?", (item_id, user["id"]))
    await db.commit()
    return {"ok": True}
