"""Job management REST API — list, trigger, and configure automated scrape jobs."""
from __future__ import annotations

from typing import Annotated, Any

import psycopg
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_conn, get_pool
from app.config import settings

log = structlog.get_logger()
router = APIRouter(prefix="/jobs", tags=["jobs"])

Conn = Annotated[psycopg.AsyncConnection, Depends(get_conn)]


class JobUpdate(BaseModel):
    enabled: bool | None = None
    cron: str | None = None


@router.get("")
async def list_jobs(conn: Conn) -> list[dict[str, Any]]:
    """Return all registered jobs with their schedule and last-run info."""
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT j.job_id, j.display_name, j.enabled, j.cron,
                   j.last_run_at, j.next_run_at, j.last_status, j.last_log_id,
                   l.items_attempted, l.items_succeeded, l.items_failed,
                   l.error_message, l.metadata
            FROM scraping.job_schedules j
            LEFT JOIN scraping.scraper_execution_logs l ON l.id = j.last_log_id
            ORDER BY j.job_id
        """)
        rows = await cur.fetchall()

    return [
        {
            "job_id": r["job_id"],
            "display_name": r["display_name"],
            "enabled": r["enabled"],
            "cron": r["cron"],
            "last_run_at": r["last_run_at"].isoformat() if r["last_run_at"] else None,
            "next_run_at": r["next_run_at"].isoformat() if r["next_run_at"] else None,
            "last_status": r["last_status"],
            "last_run_summary": {
                "items_attempted": r["items_attempted"],
                "items_succeeded": r["items_succeeded"],
                "items_failed": r["items_failed"],
                "error_message": r["error_message"],
                "metadata": r["metadata"],
            } if r["last_log_id"] else None,
        }
        for r in rows
    ]


@router.post("/{job_id}/trigger")
async def trigger_job(job_id: str, background_tasks: BackgroundTasks) -> dict:
    """Fire a job immediately (runs in background, returns immediately)."""
    from app.scheduler import trigger_job as _trigger

    async with (await get_pool()).connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT job_id FROM scraping.job_schedules WHERE job_id = %s",
                (job_id,),
            )
            row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    pool = await get_pool()
    background_tasks.add_task(_trigger, job_id, pool, settings.database_url)
    return {"status": "triggered", "job_id": job_id}


@router.patch("/{job_id}")
async def update_job(job_id: str, body: JobUpdate, conn: Conn) -> dict:
    """Enable/disable a job or change its cron schedule."""
    from app.scheduler import reload_job

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT job_id, enabled, cron FROM scraping.job_schedules WHERE job_id = %s",
            (job_id,),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    new_enabled = body.enabled if body.enabled is not None else row["enabled"]
    new_cron = body.cron if body.cron is not None else row["cron"]

    async with conn.cursor() as cur:
        await cur.execute(
            """UPDATE scraping.job_schedules
               SET enabled = %s, cron = %s
               WHERE job_id = %s""",
            (new_enabled, new_cron, job_id),
        )
        await conn.commit()

    pool = await get_pool()
    await reload_job(job_id, new_enabled, new_cron, pool, settings.database_url)

    return {"job_id": job_id, "enabled": new_enabled, "cron": new_cron}


@router.get("/{job_id}/runs")
async def get_job_runs(job_id: str, conn: Conn, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent execution history for a job."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT job_id FROM scraping.job_schedules WHERE job_id = %s", (job_id,)
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

        await cur.execute("""
            SELECT id, status, started_at, finished_at,
                   items_attempted, items_succeeded, items_failed,
                   error_message, metadata
            FROM scraping.scraper_execution_logs
            WHERE scraper_kind = 'retailer_discovery'
              AND scraper_target = %s
            ORDER BY started_at DESC
            LIMIT %s
        """, (job_id, limit))
        runs = await cur.fetchall()

    return [
        {
            "id": r["id"],
            "status": r["status"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            "items_attempted": r["items_attempted"],
            "items_succeeded": r["items_succeeded"],
            "items_failed": r["items_failed"],
            "error_message": r["error_message"],
            "metadata": r["metadata"],
        }
        for r in runs
    ]
