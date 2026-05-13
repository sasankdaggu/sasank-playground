"""Core Nykaa scrape job — shared by the scheduler and the CLI script.

Calling run_full_nykaa_scrape() is equivalent to running the old
`python -m scripts.scrape_nykaa --execute` including all auto-retries.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import psycopg
import structlog
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

log = structlog.get_logger()

FAILED_URLS_FILE = Path(__file__).resolve().parent.parent.parent / "nykaa_failed_urls.jsonl"
PRODUCT_PAGE_DELAY = 2.0


# ── Brands ────────────────────────────────────────────────────────────────────

NYKAA_BRANDS: dict[str, str] = {
    "minimalist":        "Minimalist",
    "mcaffeine":         "MCaffeine",
    "dot_and_key":       "Dot & Key",
    "the_derma_co":      "The Derma Co",
    "aqualogica":        "Aqualogica",
    "bare_necessities":  "Bare Necessities",
    "beauty_of_joseon":  "Beauty of Joseon",
    "conscious_chemist": "Conscious Chemist",
    "daughter_earth":    "Daughter Earth",
    "dermalogica_in":    "Dermalogica",
    "pilgrim":           "Pilgrim",
    "dr_sheths":         "Dr. Sheth's",
    "earth_rhythm":      "Earth Rhythm",
    "fae_beauty":        "FAE Beauty",
    "foxtale":           "Foxtale",
    "innisfree_in":      "Innisfree",
    "pixi_in":           "Pixi",
    "juicy_chemistry":   "Juicy Chemistry",
    "kiehls_in":         "Kiehl's",
    "world_of_asaya":    "Asaya",
    "paulas_choice_in":  "Paula's Choice",
    "reequil":           "Re'equil",
    "simple_in":         "Simple",
    "the_deconstruct":   "The Deconstruct",
    "the_face_shop_in":  "The Face Shop",
    "the_pink_foundry":  "The Pink Foundry",
    "fixderma":          "Fixderma",
    "lotus":             "Lotus Herbals",
    "ponds_in":          "Pond's",
    "forest_essentials": "Forest Essentials",
    "kama_ayurveda":     "Kama Ayurveda",
    "cetaphil_in":       "Cetaphil",
    "neutrogena_in":     "Neutrogena",
    "mamaearth":         "Mamaearth",
    "nathabit":          "Nathabit",
    "be_bodywise":       "Be Bodywise",
    "plix":              "Plix",
    "thebodyshop_in":    "The Body Shop",
    "olay_in":           "Olay",
    "cerave_in":         "CeraVe",
    "bioderma_in":       "Bioderma",
}


# ── Connection helpers ────────────────────────────────────────────────────────

async def _conn_from_pool(pool: AsyncConnectionPool) -> psycopg.AsyncConnection:
    return await pool.getconn()


async def _release(pool: AsyncConnectionPool, conn: psycopg.AsyncConnection) -> None:
    await pool.putconn(conn)


async def _fresh_conn(db_url: str) -> psycopg.AsyncConnection:
    dsn = db_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)


# ── Execution log helpers ─────────────────────────────────────────────────────

async def _log_start(pool: AsyncConnectionPool, job_id: str) -> int:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO scraping.scraper_execution_logs
                   (scraper_kind, scraper_target, status, started_at)
                   VALUES ('retailer_discovery', %s, 'running', now())
                   RETURNING id""",
                (job_id,),
            )
            row = await cur.fetchone()
            await conn.commit()
    return row["id"]


async def _log_finish(
    pool: AsyncConnectionPool,
    log_id: int,
    status: str,
    items_attempted: int,
    items_succeeded: int,
    items_failed: int,
    error_message: str | None = None,
    metadata: dict | None = None,
) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """UPDATE scraping.scraper_execution_logs
                   SET status=%s, finished_at=now(),
                       items_attempted=%s, items_succeeded=%s, items_failed=%s,
                       error_message=%s, metadata=%s
                   WHERE id=%s""",
                (status, items_attempted, items_succeeded, items_failed,
                 error_message, json.dumps(metadata or {}), log_id),
            )
            await conn.commit()
    # Update job_schedules with latest run info
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """UPDATE scraping.job_schedules
                   SET last_run_at=now(), last_status=%s, last_log_id=%s
                   WHERE job_id='nykaa_scrape'""",
                (status, log_id),
            )
            await conn.commit()


# ── Brand scrape (same logic as scripts/scrape_nykaa.py run_brand) ────────────

async def _run_brand(
    slug: str,
    search_name: str,
    limit: int,
    db_url: str,
    retailer_id: int,
    proxy_url: str,
    proxy_user: str,
    proxy_pass: str,
    scraperapi_key: str,
) -> tuple[int, list[dict]]:
    from scraper.fetchers.nykaa import fetch_nykaa_brand_product_urls, fetch_nykaa_page
    from scraper.parsers.nykaa import parse_nykaa_product
    from scraper.db import upsert_product
    from scraper.retailers import retailer_by_slug

    retailer = retailer_by_slug("nykaa")
    log.info("nykaa_brand_start", brand=slug)

    discovered = await fetch_nykaa_brand_product_urls(search_name, scraperapi_key, limit=limit)
    if not discovered:
        log.warning("nykaa_brand_no_urls", brand=slug)
        return 0, []

    log.info("nykaa_brand_urls_found", brand=slug, count=len(discovered))

    conn = await _fresh_conn(db_url)
    ok = 0
    failed: list[dict] = []

    try:
        for i, item in enumerate(discovered):
            url = item["url"]
            html = await fetch_nykaa_page(url, proxy_url, proxy_user, proxy_pass)
            if not html:
                failed.append({"url": url, "name": item.get("name", ""), "brand": slug})
                await asyncio.sleep(PRODUCT_PAGE_DELAY)
                continue

            product = parse_nykaa_product(html, url)
            if not product.canonical_name:
                await asyncio.sleep(PRODUCT_PAGE_DELAY)
                continue

            try:
                await upsert_product(conn, product, retailer, retailer_id)
                ok += 1
            except Exception as exc:
                log.error("nykaa_upsert_error", brand=slug, error=str(exc))
                try:
                    await conn.rollback()
                except Exception:
                    try:
                        await conn.close()
                    except Exception:
                        pass
                    conn = await _fresh_conn(db_url)

            if (i + 1) % 20 == 0:
                log.info("nykaa_brand_progress", brand=slug, done=i + 1,
                         total=len(discovered), upserted=ok)
            await asyncio.sleep(PRODUCT_PAGE_DELAY)
    finally:
        try:
            await conn.close()
        except Exception:
            pass

    log.info("nykaa_brand_done", brand=slug, upserted=ok, failed=len(failed))
    return ok, failed


async def _run_retry_failed(
    db_url: str,
    retailer_id: int,
    scraperapi_key: str,
) -> int:
    from scraper.fetchers.nykaa import fetch_nykaa_page_scraperapi
    from scraper.parsers.nykaa import parse_nykaa_product
    from scraper.db import upsert_product
    from scraper.retailers import retailer_by_slug

    if not FAILED_URLS_FILE.exists():
        return 0

    items = [json.loads(l) for l in FAILED_URLS_FILE.read_text().splitlines() if l.strip()]
    log.info("nykaa_retry_start", count=len(items))

    retailer = retailer_by_slug("nykaa")
    conn = await _fresh_conn(db_url)
    ok = 0
    still_failed: list[dict] = []

    try:
        for item in items:
            url = item["url"]
            html = await fetch_nykaa_page_scraperapi(url, scraperapi_key)
            if not html:
                still_failed.append(item)
                await asyncio.sleep(1.0)
                continue

            product = parse_nykaa_product(html, url)
            if not product.canonical_name:
                await asyncio.sleep(1.0)
                continue

            try:
                await upsert_product(conn, product, retailer, retailer_id)
                ok += 1
            except Exception as exc:
                log.error("nykaa_retry_upsert_error", error=str(exc))
                await conn.rollback()
                still_failed.append(item)

            await asyncio.sleep(1.0)
    finally:
        try:
            await conn.close()
        except Exception:
            pass

    if still_failed:
        FAILED_URLS_FILE.write_text("\n".join(json.dumps(x) for x in still_failed) + "\n")
    else:
        FAILED_URLS_FILE.unlink(missing_ok=True)

    log.info("nykaa_retry_done", upserted=ok, still_failed=len(still_failed))
    return ok


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_full_nykaa_scrape(
    pool: AsyncConnectionPool,
    db_url: str,
    limit: int = 300,
    brand_slugs: list[str] | None = None,
) -> dict[str, Any]:
    """
    Full Nykaa scrape: discover URLs → fetch pages → upsert → retry crashes
    → retry Akamai failures via ScraperAPI.

    Returns a summary dict logged to scraper_execution_logs.
    """
    from app.config import settings
    from scraper.db import ensure_retailers

    proxy_url = settings.proxy_url
    proxy_user = settings.proxy_user
    proxy_pass = settings.proxy_pass
    scraperapi_key = settings.scraperapi_key

    if not proxy_url or not proxy_user or not proxy_pass:
        raise RuntimeError("Smartproxy not configured (PROXY_URL/PROXY_USER/PROXY_PASS missing)")

    brands = {
        slug: name for slug, name in NYKAA_BRANDS.items()
        if brand_slugs is None or slug in brand_slugs
    }

    # Resolve retailer ID
    async with pool.connection() as conn:
        retailer_ids = await ensure_retailers(conn)
    retailer_id = retailer_ids.get("nykaa", 0)

    log_id = await _log_start(pool, "nykaa_scrape")
    log.info("nykaa_job_start", brands=list(brands.keys()), limit=limit)

    total = 0
    all_failed: list[dict] = []
    fatal_brands: list[str] = []

    # ── Pass 1: all brands ────────────────────────────────────────────────────
    for slug, search_name in brands.items():
        try:
            brand_total, brand_failed = await _run_brand(
                slug, search_name, limit, db_url, retailer_id,
                proxy_url, proxy_user, proxy_pass, scraperapi_key,
            )
            total += brand_total
            all_failed.extend(brand_failed)
        except Exception as exc:
            log.error("nykaa_brand_fatal", brand=slug, error=str(exc))
            fatal_brands.append(slug)

    # ── Pass 2: retry fatally-crashed brands ──────────────────────────────────
    if fatal_brands:
        log.info("nykaa_retrying_fatal_brands", brands=fatal_brands)
        for slug in fatal_brands:
            try:
                brand_total, brand_failed = await _run_brand(
                    slug, brands[slug], limit, db_url, retailer_id,
                    proxy_url, proxy_user, proxy_pass, scraperapi_key,
                )
                total += brand_total
                all_failed.extend(brand_failed)
                log.info("nykaa_fatal_brand_recovered", brand=slug)
            except Exception as exc:
                log.error("nykaa_fatal_brand_retry_failed", brand=slug, error=str(exc))

    # ── Persist failed URLs ───────────────────────────────────────────────────
    if all_failed:
        existing: list[dict] = []
        if FAILED_URLS_FILE.exists():
            existing = [json.loads(l) for l in FAILED_URLS_FILE.read_text().splitlines() if l.strip()]
        existing_urls = {x["url"] for x in existing}
        combined = existing + [x for x in all_failed if x["url"] not in existing_urls]
        FAILED_URLS_FILE.write_text("\n".join(json.dumps(x) for x in combined) + "\n")

    # ── Pass 3: ScraperAPI retry for Akamai-blocked URLs ─────────────────────
    retried = 0
    if all_failed and scraperapi_key:
        log.info("nykaa_auto_retry_akamai", count=len(all_failed))
        retried = await _run_retry_failed(db_url, retailer_id, scraperapi_key)
    elif all_failed and not scraperapi_key:
        log.warning("scraperapi_not_configured_skipping_retry")

    summary = {
        "total_upserted": total,
        "akamai_blocked": len(all_failed),
        "akamai_recovered": retried,
        "fatal_brands": fatal_brands,
        "brands_scraped": list(brands.keys()),
    }
    status = "failed" if total == 0 else ("partial" if all_failed else "success")
    await _log_finish(
        pool, log_id, status,
        items_attempted=total + len(all_failed),
        items_succeeded=total,
        items_failed=len(all_failed) - retried,
        metadata=summary,
    )
    log.info("nykaa_job_done", **summary)
    return summary
