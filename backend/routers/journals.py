from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite, uuid, httpx, json, os
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree

from database import get_db
from routers.users import get_current_user

router = APIRouter(prefix="/journals", tags=["journals"])

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_TOOL    = "JournalClubApp"
PUBMED_EMAIL   = os.environ.get("PUBMED_EMAIL", "")  # required by NCBI ToS

# In-memory TOC cache: key=(journal_id, months) → (fetched_at, articles)
_toc_cache: dict[tuple, tuple] = {}
CACHE_TTL_HOURS = 6


class CustomJournalRequest(BaseModel):
    full_name: str
    abbreviation: str
    issn: str


def _cache_key(journal_id: str, months: int) -> tuple:
    return (journal_id, months)


def _cache_fresh(key: tuple) -> list | None:
    if key not in _toc_cache:
        return None
    fetched_at, articles = _toc_cache[key]
    if datetime.now(timezone.utc) - fetched_at > timedelta(hours=CACHE_TTL_HOURS):
        del _toc_cache[key]
        return None
    return articles


async def _fetch_pubmed_toc(issn: str, months: int, abbreviation: str = "") -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=months * 31)).strftime("%Y/%m/%d")
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    date_filter = f'("{since}"[PDAT]:"{today}"[PDAT])'

    async with httpx.AsyncClient(timeout=20) as client:
        # Step 1: esearch — get PMIDs by ISSN
        r = await client.get(PUBMED_ESEARCH, params={
            "db": "pubmed",
            "term": f'"{issn}"[ISSN] AND {date_filter}',
            "retmax": 100,
            "retmode": "json",
            "sort": "pub+date",
            "tool": PUBMED_TOOL,
            "email": PUBMED_EMAIL,
        })
        r.raise_for_status()
        data = r.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])

        # Fallback: search by journal title abbreviation [TA] if ISSN returned nothing
        if not pmids and abbreviation:
            r2a = await client.get(PUBMED_ESEARCH, params={
                "db": "pubmed",
                "term": f'"{abbreviation}"[TA] AND {date_filter}',
                "retmax": 100,
                "retmode": "json",
                "sort": "pub+date",
                "tool": PUBMED_TOOL,
                "email": PUBMED_EMAIL,
            })
            r2a.raise_for_status()
            pmids = r2a.json().get("esearchresult", {}).get("idlist", [])

        if not pmids:
            return []

        # Step 2: efetch — get article details
        r2 = await client.get(PUBMED_EFETCH, params={
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "tool": PUBMED_TOOL,
            "email": PUBMED_EMAIL,
        })
        r2.raise_for_status()

    root = ElementTree.fromstring(r2.text)
    articles = []
    for art in root.findall(".//PubmedArticle"):
        try:
            medline = art.find("MedlineCitation")
            article = medline.find("Article")

            title = article.findtext("ArticleTitle") or ""
            abstract_el = article.find("Abstract/AbstractText")
            abstract = abstract_el.text if abstract_el is not None else None

            authors = []
            for a in article.findall("AuthorList/Author"):
                last = a.findtext("LastName") or ""
                fore = a.findtext("ForeName") or a.findtext("Initials") or ""
                name = f"{last} {fore}".strip()
                if name:
                    authors.append(name)

            pmid = medline.findtext("PMID") or ""
            journal_el = article.find("Journal")
            journal_name = journal_el.findtext("Title") or "" if journal_el is not None else ""
            pub_date_el = (
                journal_el.find("JournalIssue/PubDate") if journal_el is not None else None
            )
            if pub_date_el is not None:
                year  = pub_date_el.findtext("Year") or ""
                month = pub_date_el.findtext("Month") or ""
                pub_date = f"{year} {month}".strip()
            else:
                pub_date = ""

            doi = None
            for aid in art.findall(".//ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text
                    break

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            articles.append({
                "pmid": pmid,
                "title": title,
                "authors": authors,
                "journal": journal_name,
                "pub_date": pub_date,
                "abstract": abstract,
                "doi": doi,
                "url": url,
            })
        except Exception:
            continue

    return articles


@router.get("/")
async def list_journals(user=Depends(get_current_user), db=Depends(get_db)):
    async with db.execute("SELECT * FROM journals ORDER BY category, full_name") as cur:
        journals = [dict(r) for r in await cur.fetchall()]
    async with db.execute(
        "SELECT journal_id FROM journal_follows WHERE user_id=?", (user["id"],)
    ) as cur:
        followed = {r["journal_id"] for r in await cur.fetchall()}
    for j in journals:
        j["is_following"] = j["id"] in followed
    return journals


@router.post("/{journal_id}/follow", status_code=201)
async def follow_journal(journal_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.execute("SELECT id FROM journals WHERE id=?", (journal_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Journal not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR IGNORE INTO journal_follows (user_id, journal_id, followed_at) VALUES (?,?,?)",
        (user["id"], journal_id, now),
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{journal_id}/follow")
async def unfollow_journal(journal_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    await db.execute(
        "DELETE FROM journal_follows WHERE user_id=? AND journal_id=?",
        (user["id"], journal_id),
    )
    await db.commit()
    return {"ok": True}


@router.get("/{journal_id}/toc")
async def get_journal_toc(
    journal_id: str,
    months: int = 1,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    if months not in (1, 3, 6, 12):
        months = 1
    async with db.execute("SELECT * FROM journals WHERE id=?", (journal_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Journal not found")

    key = _cache_key(journal_id, months)
    cached = _cache_fresh(key)
    if cached is not None:
        return cached

    articles = await _fetch_pubmed_toc(row["issn"], months, row["abbreviation"])
    _toc_cache[key] = (datetime.now(timezone.utc), articles)
    return articles


@router.post("/custom", status_code=201)
async def add_custom_journal(
    req: CustomJournalRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    journal_id = req.abbreviation.lower().replace(" ", "-").replace("/", "-")
    await db.execute(
        "INSERT OR IGNORE INTO journals (id, full_name, abbreviation, issn, category) VALUES (?,?,?,?,?)",
        (journal_id, req.full_name, req.abbreviation, req.issn, "custom"),
    )
    await db.commit()
    return {"id": journal_id, "full_name": req.full_name, "abbreviation": req.abbreviation,
            "issn": req.issn, "category": "custom", "is_following": False}
