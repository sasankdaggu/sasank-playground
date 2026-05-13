"""Ingredient detail extraction pipeline (Layer 2).

Iterates `core.ingredients`, fetches per-source detail records, writes to
`core.ingredient_detail_sources`, and merges into `core.ingredient_detail`.

Currently wires INCIDecoder (P0). EWG / CosIng / COSDNA can be added by registering
a fetcher in SOURCE_FETCHERS.

Usage:
  python -m scraper.run_ingredient_detail                 # all active sources, all ingredients
  python -m scraper.run_ingredient_detail --source incidecoder --limit 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app.config import settings  # noqa: E402
from scraper.execution_log import record_run  # noqa: E402
from scraper.fetchers.ingredient_detail_incidecoder import fetch_incidecoder  # noqa: E402

log = structlog.get_logger()


# Each fetcher returns a dict with: source, source_url, fetch_status, plus normalized fields.
SOURCE_FETCHERS = {
    "incidecoder": fetch_incidecoder,
}


async def _get_conn():
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)


async def _fetch_active_sources(conn) -> list[str]:
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT source FROM scraping.ingredient_source_strategies
            WHERE status = 'active'
        """)
        return [r["source"] for r in await cur.fetchall() if r["source"] in SOURCE_FETCHERS]


async def _fetch_targets(conn, source: str, limit: int) -> list[dict]:
    """Pick ingredients that don't yet have a successful row from this source."""
    limit_clause = f"LIMIT {limit}" if limit else ""
    async with conn.cursor() as cur:
        await cur.execute(f"""
            SELECT i.id, i.inci_name
            FROM core.ingredients i
            LEFT JOIN core.ingredient_detail_sources s
              ON s.ingredient_id = i.id AND s.source = %s
            WHERE s.id IS NULL OR s.fetch_status = 'failed'
            ORDER BY i.id
            {limit_clause}
        """, (source,))
        return await cur.fetchall()


async def _save_source_row(conn, ingredient_id: int, source: str, payload: dict) -> None:
    """Upsert a per-source row."""
    async with conn.cursor() as cur:
        await cur.execute("""
            INSERT INTO core.ingredient_detail_sources
              (ingredient_id, source, source_url, source_id,
               inci_name, cas_number, ec_number, iupac_name,
               functions, description,
               id_rating, raw_payload, fetched_at, fetch_status, error_message)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s)
            ON CONFLICT (ingredient_id, source) DO UPDATE SET
              source_url = EXCLUDED.source_url,
              inci_name  = EXCLUDED.inci_name,
              cas_number = COALESCE(EXCLUDED.cas_number, core.ingredient_detail_sources.cas_number),
              ec_number  = COALESCE(EXCLUDED.ec_number, core.ingredient_detail_sources.ec_number),
              iupac_name = COALESCE(EXCLUDED.iupac_name, core.ingredient_detail_sources.iupac_name),
              functions  = EXCLUDED.functions,
              description = COALESCE(EXCLUDED.description, core.ingredient_detail_sources.description),
              id_rating  = COALESCE(EXCLUDED.id_rating, core.ingredient_detail_sources.id_rating),
              raw_payload = EXCLUDED.raw_payload,
              fetched_at = now(),
              fetch_status = EXCLUDED.fetch_status,
              error_message = EXCLUDED.error_message
        """, (
            ingredient_id, source, payload.get("source_url"), payload.get("source_id"),
            payload.get("inci_name"), payload.get("cas_number"), payload.get("ec_number"),
            payload.get("iupac_name"),
            payload.get("functions") or None,
            payload.get("description"),
            payload.get("id_rating"),
            json.dumps({k: v for k, v in payload.items() if k != "raw_payload"}),
            payload.get("fetch_status", "failed"),
            payload.get("error_message"),
        ))


async def _merge_ingredient_detail(conn, ingredient_id: int) -> None:
    """Collate per-source rows into core.ingredient_detail."""
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT source, source_url, cas_number, ec_number, functions, description,
                   id_rating, ewg_hazard_low, ewg_hazard_high, ewg_concerns,
                   cosdna_acne, cosdna_irritant, cosing_annex, cosing_restriction
            FROM core.ingredient_detail_sources
            WHERE ingredient_id = %s AND fetch_status = 'success'
        """, (ingredient_id,))
        rows = await cur.fetchall()

    if not rows:
        return

    sources_used = sorted({r["source"] for r in rows})
    citation_urls = {r["source"]: r["source_url"] for r in rows}
    cas = next((r["cas_number"] for r in rows if r["cas_number"]), None)
    ec = next((r["ec_number"] for r in rows if r["ec_number"]), None)
    # Description: prefer INCIDecoder for plain-English
    desc = next((r["description"] for r in rows
                 if r["source"] == "incidecoder" and r["description"]), None) \
        or next((r["description"] for r in rows if r["description"]), None)
    desc_source = next((r["source"] for r in rows if r["description"] == desc), None)

    funcs = sorted({f for r in rows for f in (r["functions"] or [])})

    ewg = next((r for r in rows if r["source"] == "ewg"), None)
    cosdna = next((r for r in rows if r["source"] == "cosdna"), None)
    cosing = next((r for r in rows if r["source"] == "cosing"), None)
    incidecoder = next((r for r in rows if r["source"] == "incidecoder"), None)

    confidence = round(len(sources_used) / 4, 2)

    async with conn.cursor() as cur:
        await cur.execute("""
            INSERT INTO core.ingredient_detail
              (ingredient_id, cas_number, ec_number, description, description_source,
               functions, ewg_hazard_low, ewg_hazard_high, ewg_concerns,
               cosdna_acne, cosdna_irritant, cosing_annex, cosing_restriction, id_rating,
               sources_used, citation_urls, confidence_score, collated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (ingredient_id) DO UPDATE SET
              cas_number=EXCLUDED.cas_number, ec_number=EXCLUDED.ec_number,
              description=EXCLUDED.description, description_source=EXCLUDED.description_source,
              functions=EXCLUDED.functions,
              ewg_hazard_low=EXCLUDED.ewg_hazard_low, ewg_hazard_high=EXCLUDED.ewg_hazard_high,
              ewg_concerns=EXCLUDED.ewg_concerns,
              cosdna_acne=EXCLUDED.cosdna_acne, cosdna_irritant=EXCLUDED.cosdna_irritant,
              cosing_annex=EXCLUDED.cosing_annex, cosing_restriction=EXCLUDED.cosing_restriction,
              id_rating=EXCLUDED.id_rating,
              sources_used=EXCLUDED.sources_used, citation_urls=EXCLUDED.citation_urls,
              confidence_score=EXCLUDED.confidence_score, collated_at=now()
        """, (
            ingredient_id, cas, ec, desc, desc_source, funcs,
            ewg["ewg_hazard_low"] if ewg else None,
            ewg["ewg_hazard_high"] if ewg else None,
            json.dumps(ewg["ewg_concerns"]) if ewg and ewg["ewg_concerns"] else None,
            cosdna["cosdna_acne"] if cosdna else None,
            cosdna["cosdna_irritant"] if cosdna else None,
            cosing["cosing_annex"] if cosing else None,
            cosing["cosing_restriction"] if cosing else None,
            incidecoder["id_rating"] if incidecoder else None,
            sources_used, json.dumps(citation_urls), confidence,
        ))


async def run_one_source(conn, source: str, limit: int, concurrency: int, dry_run: bool):
    fetcher = SOURCE_FETCHERS[source]
    targets = await _fetch_targets(conn, source, limit)
    if not targets:
        log.info("ingredient_detail_no_targets", source=source)
        return {"attempted": 0, "succeeded": 0, "failed": 0}

    log.info("ingredient_detail_run_start", source=source, total=len(targets), dry_run=dry_run)

    sem = asyncio.Semaphore(concurrency)
    counts = {"attempted": 0, "succeeded": 0, "failed": 0, "not_found": 0}

    async def worker(ing):
        async with sem:
            counts["attempted"] += 1
            payload = await fetcher(ing["inci_name"])
            if not payload:
                counts["failed"] += 1
                return
            status = payload.get("fetch_status")
            if status == "success":
                counts["succeeded"] += 1
                if not dry_run:
                    await _save_source_row(conn, ing["id"], source, payload)
                    await _merge_ingredient_detail(conn, ing["id"])
                    await conn.commit()
            elif status == "not_found":
                counts["not_found"] += 1
                if not dry_run:
                    await _save_source_row(conn, ing["id"], source, payload)
                    await conn.commit()
            else:
                counts["failed"] += 1
                if not dry_run:
                    await _save_source_row(conn, ing["id"], source, payload)
                    await conn.commit()
            await asyncio.sleep(1.5)  # respect rate limit

    await asyncio.gather(*(worker(t) for t in targets))
    log.info("ingredient_detail_run_complete", source=source, **counts)
    return counts


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--source", help="Run a single source (e.g. incidecoder)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


async def main():
    args = _parse_args()
    conn = await _get_conn()
    try:
        sources = [args.source] if args.source else await _fetch_active_sources(conn)
        for source in sources:
            if source not in SOURCE_FETCHERS:
                log.warning("no_fetcher_for_source", source=source)
                continue
            counts = await run_one_source(conn, source, args.limit, args.concurrency, args.dry_run)
            if not args.dry_run and counts["attempted"]:
                if counts["failed"] == 0:
                    s = "success"
                elif counts["succeeded"] == 0:
                    s = "failed"
                else:
                    s = "partial"
                await record_run("ingredient_detail", source, status=s,
                                 items_attempted=counts["attempted"],
                                 items_succeeded=counts["succeeded"],
                                 items_failed=counts["failed"])
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
