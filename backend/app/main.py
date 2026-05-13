from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import close_pool, get_pool
from app.routers import auth, ingredients, jobs, products, scraper_status, shelf
from app.scheduler import start_scheduler, stop_scheduler

log = structlog.get_logger()

app = FastAPI(title="Wand API", version="0.1.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(shelf.router)
app.include_router(auth.router)
app.include_router(scraper_status.router)
app.include_router(ingredients.router)
app.include_router(jobs.router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/dashboard")
async def dashboard() -> FileResponse:
    return FileResponse(_STATIC_DIR / "scraper_status.html")


@app.get("/ingredient")
async def ingredient_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "ingredient.html")


@app.on_event("startup")
async def startup() -> None:
    pool = await get_pool()
    await start_scheduler(pool, settings.database_url)
    log.info("wand_api_started")


@app.on_event("shutdown")
async def shutdown() -> None:
    stop_scheduler()
    await close_pool()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
