"""APScheduler integration — loads job_schedules from DB and registers cron jobs."""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from psycopg_pool import AsyncConnectionPool

log = structlog.get_logger()

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def _run_nykaa(pool: AsyncConnectionPool, db_url: str) -> None:
    from scraper.jobs.nykaa import run_full_nykaa_scrape
    log.info("scheduler_firing_nykaa")
    try:
        summary = await run_full_nykaa_scrape(pool, db_url)
        log.info("scheduler_nykaa_done", **summary)
    except Exception as exc:
        log.error("scheduler_nykaa_error", error=str(exc))


_JOB_RUNNERS: dict[str, Any] = {
    "nykaa_scrape": _run_nykaa,
}


async def start_scheduler(pool: AsyncConnectionPool, db_url: str) -> None:
    scheduler = get_scheduler()

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT job_id, enabled, cron FROM scraping.job_schedules"
            )
            jobs = await cur.fetchall()

    for job in jobs:
        if not job["enabled"] or not job["cron"]:
            log.info("scheduler_job_skipped", job_id=job["job_id"],
                     reason="disabled" if not job["enabled"] else "no_cron")
            continue

        runner = _JOB_RUNNERS.get(job["job_id"])
        if runner is None:
            log.warning("scheduler_unknown_job", job_id=job["job_id"])
            continue

        scheduler.add_job(
            lambda p=pool, d=db_url, r=runner: asyncio.ensure_future(r(p, d)),
            trigger=CronTrigger.from_crontab(job["cron"]),
            id=job["job_id"],
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info("scheduler_job_registered", job_id=job["job_id"], cron=job["cron"])

    scheduler.start()
    log.info("scheduler_started", job_count=len([j for j in jobs if j["enabled"] and j["cron"]]))


async def trigger_job(job_id: str, pool: AsyncConnectionPool, db_url: str) -> None:
    runner = _JOB_RUNNERS.get(job_id)
    if runner is None:
        raise ValueError(f"Unknown job: {job_id}")
    asyncio.ensure_future(runner(pool, db_url))
    log.info("scheduler_job_triggered", job_id=job_id)


async def reload_job(
    job_id: str,
    enabled: bool,
    cron: str | None,
    pool: AsyncConnectionPool,
    db_url: str,
) -> None:
    scheduler = get_scheduler()
    scheduler.remove_job(job_id, jobstore=None)

    if not enabled or not cron:
        log.info("scheduler_job_unscheduled", job_id=job_id)
        return

    runner = _JOB_RUNNERS.get(job_id)
    if runner is None:
        return

    scheduler.add_job(
        lambda p=pool, d=db_url, r=runner: asyncio.ensure_future(r(p, d)),
        trigger=CronTrigger.from_crontab(cron),
        id=job_id,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    log.info("scheduler_job_rescheduled", job_id=job_id, cron=cron)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler_stopped")
    _scheduler = None
