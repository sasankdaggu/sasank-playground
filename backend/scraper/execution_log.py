"""Helpers for recording scraper run health into scraping.scraper_execution_logs.

Each scraper invocation should wrap its body in `log_run(kind, target)` so the
status dashboard can show recent uptime, last success, and per-day history.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg

from app.config import settings


def _dsn() -> str:
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


@asynccontextmanager
async def log_run(scraper_kind: str, scraper_target: str, *, metadata: dict | None = None):
    """Wrap a scraper run; record success/failure into scraper_execution_logs.

    Yields a mutable counter dict — set ``counter['attempted']``, ``counter['succeeded']``,
    ``counter['failed']`` inside the block and the values are persisted.

    Usage:
        async with log_run("ingredient_extract", "beminimalist.co") as counter:
            for product in products:
                counter["attempted"] += 1
                if extract(product):
                    counter["succeeded"] += 1
                else:
                    counter["failed"] += 1
    """
    counter = {"attempted": 0, "succeeded": 0, "failed": 0}
    started_at = datetime.now(timezone.utc)

    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO scraping.scraper_execution_logs
                  (scraper_kind, scraper_target, status, started_at, metadata)
                VALUES (%s, %s, 'running', %s, %s)
                RETURNING id
            """, (scraper_kind, scraper_target, started_at, json.dumps(metadata or {})))
            row = await cur.fetchone()
            log_id = row["id"] if row and "id" in row else (row[0] if row else None)
        await conn.commit()

    error: BaseException | None = None
    try:
        yield counter
    except BaseException as e:  # noqa: BLE001
        error = e
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        attempted = counter["attempted"]
        succeeded = counter["succeeded"]
        failed = counter["failed"]
        if error is not None:
            status = "failed"
        elif attempted == 0:
            status = "no_data"
        elif failed == 0:
            status = "success"
        elif succeeded == 0:
            status = "failed"
        else:
            status = "partial"

        async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scraping.scraper_execution_logs
                    SET status = %s, finished_at = %s,
                        items_attempted = %s, items_succeeded = %s, items_failed = %s,
                        error_message = %s
                    WHERE id = %s
                """, (status, finished_at, attempted, succeeded, failed,
                      str(error) if error else None, log_id))
            await conn.commit()


async def record_run(
    scraper_kind: str,
    scraper_target: str,
    *,
    status: str,
    items_attempted: int = 0,
    items_succeeded: int = 0,
    items_failed: int = 0,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """One-shot logger for synchronous record-keeping (e.g. in the worker loop)."""
    now = datetime.now(timezone.utc)
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO scraping.scraper_execution_logs
                  (scraper_kind, scraper_target, status,
                   started_at, finished_at,
                   items_attempted, items_succeeded, items_failed,
                   error_message, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (scraper_kind, scraper_target, status, now, now,
                  items_attempted, items_succeeded, items_failed,
                  error_message, json.dumps(metadata or {})))
        await conn.commit()
