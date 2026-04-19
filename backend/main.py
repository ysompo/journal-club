from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import shutil, os, glob
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db
from config import FRONTEND_ORIGINS, DB_PATH, APP_VERSION
from routers import users, articles, queue, devices, settings, admin

scheduler = AsyncIOScheduler(timezone="UTC")


async def _backup_db():
    if not os.path.exists(DB_PATH):
        return
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    backup_path = f"{DB_PATH}.backup.{date_str}"
    shutil.copy2(DB_PATH, backup_path)
    # Keep last 7 backups
    pattern = f"{DB_PATH}.backup.*"
    old_backups = sorted(glob.glob(pattern), reverse=True)[7:]
    for path in old_backups:
        os.remove(path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.add_job(_backup_db, "cron", hour=3, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Journal Club API", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(articles.router)
app.include_router(queue.router)
app.include_router(devices.router)
app.include_router(settings.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/version")
async def version():
    return {"version": APP_VERSION, "min_client_version": "0.1.0"}
