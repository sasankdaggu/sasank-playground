"""Ingredient extraction pipeline — scrapes INCI lists from D2C brand product pages.

Reads from scraping.ingredient_extraction_queue (populated during D2C product scraping),
fetches each product page, extracts the INCI ingredient list, and stores it in
core.products.ingredients_raw.

Brand-specific logic (selectors, JS requirements) lives in scraping.ingredient_strategies.
Brands with status='no_inci' are immediately marked no_inci_html without a network request.

Usage:
  python -m scraper.run_ingredients                         # process all pending D2C entries
  python -m scraper.run_ingredients --limit 50              # process at most 50 entries
  python -m scraper.run_ingredients --retailers minimalist  # one brand only
  python -m scraper.run_ingredients --dry-run               # fetch + extract, no DB writes
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app.config import settings  # noqa: E402
from scraper.execution_log import record_run  # noqa: E402
from scraper.fetchers.ingredient_extractor import fetch_ingredient_text  # noqa: E402

log = structlog.get_logger()


def _domain_from_url(url: str) -> str:
    """Extract bare domain (no www.) from a URL."""
    netloc = urlparse(url).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def _find_strategy(listing_url: str, strategies: dict) -> dict | None:
    return strategies.get(_domain_from_url(listing_url))


async def _load_strategies(conn: psycopg.AsyncConnection) -> dict[str, dict]:
    """Return domain → strategy dict for active, needs_review, and no_inci brands."""
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT brand_domain, css_selector, requires_js, status
            FROM scraping.ingredient_strategies
            WHERE status IN ('active', 'needs_review', 'no_inci')
        """)
        return {r["brand_domain"]: dict(r) for r in await cur.fetchall()}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract INCI ingredient lists from D2C product pages")
    p.add_argument("--limit", type=int, default=0, help="Max entries to process (0=all)")
    p.add_argument("--retailers", nargs="*",
                   help="Retailer slugs to process (default: all extractable D2C brands)")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch and extract but skip DB writes")
    p.add_argument("--concurrency", type=int, default=3,
                   help="Number of concurrent fetch workers (default: 3)")
    return p.parse_args()


async def _get_conn() -> psycopg.AsyncConnection:
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(
        dsn, row_factory=psycopg.rows.dict_row,
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )


async def _fetch_pending(
    conn: psycopg.AsyncConnection,
    target_slugs: set[str] | None,
    limit: int,
) -> list[dict]:
    """Fetch pending queue entries, optionally filtered to specific retailer slugs."""
    limit_clause = f"LIMIT {limit}" if limit else ""
    slug_clause = "AND r.slug = ANY(%s)" if target_slugs else ""
    params = (list(target_slugs),) if target_slugs else ()
    async with conn.cursor() as cur:
        await cur.execute(f"""
            SELECT
                q.id          AS queue_id,
                q.product_id,
                q.listing_id,
                rl.listing_url,
                r.slug        AS retailer_slug
            FROM scraping.ingredient_extraction_queue q
            JOIN core.retailer_listings rl ON rl.id = q.listing_id
            JOIN core.retailers r ON r.id = rl.retailer_id
            WHERE q.status = 'pending'
              {slug_clause}
            ORDER BY q.created_at
            {limit_clause}
        """, params)
        return await cur.fetchall()


async def _save_result(
    conn: psycopg.AsyncConnection,
    queue_id: int,
    product_id: int,
    inci_text: str | None,
    status: str,
) -> None:
    if inci_text:
        inci_text = inci_text.replace("\x00", "")
    async with conn.cursor() as cur:
        await cur.execute("""
            UPDATE scraping.ingredient_extraction_queue
            SET status = %s, extracted_text = %s, attempts = attempts + 1
            WHERE id = %s
        """, (status, inci_text, queue_id))

        if inci_text:
            await cur.execute("""
                UPDATE core.products
                SET ingredients_raw = %s, ingredient_scrape_status = 'done'
                WHERE id = %s AND (ingredients_raw IS NULL OR ingredients_raw = '')
            """, (inci_text, product_id))
        elif status == "no_inci_html":
            await cur.execute("""
                UPDATE core.products
                SET ingredient_scrape_status = 'no_inci_html'
                WHERE id = %s AND ingredient_scrape_status = 'pending'
            """, (product_id,))
        else:
            # failed — bump attempts but leave ingredient_scrape_status as pending
            pass

    await conn.commit()


async def _worker(
    sem: asyncio.Semaphore,
    row: dict,
    dry_run: bool,
    conn: psycopg.AsyncConnection | None,
    results: dict,
    strategies: dict,
    per_brand: dict,
) -> None:
    async with sem:
        slug = row["retailer_slug"]
        url = row["listing_url"]

        strategy = _find_strategy(url, strategies)
        brand_dom = _domain_from_url(url)
        per_brand.setdefault(brand_dom, {"attempted": 0, "succeeded": 0, "failed": 0})
        per_brand[brand_dom]["attempted"] += 1

        # Brands with no_inci status are marked immediately without a network request
        if strategy and strategy.get("status") == "no_inci":
            log.info("ingredient_skip_no_inci", retailer=slug, url=url)
            if not dry_run and conn:
                await _save_result(conn, row["queue_id"], row["product_id"], None, "no_inci_html")
            results["no_inci"] = results.get("no_inci", 0) + 1
            per_brand[brand_dom]["succeeded"] += 1
            return

        inci = await fetch_ingredient_text(url, slug, strategy=strategy)

        if dry_run:
            status = "found" if inci else "not_found"
            log.info("ingredient_dry_run",
                     retailer=slug, url=url, status=status,
                     preview=(inci[:80] if inci else None))
            results[status] = results.get(status, 0) + 1
            return

        if inci:
            await _save_result(conn, row["queue_id"], row["product_id"], inci, "done")
            log.info("ingredient_saved", retailer=slug, url=url, chars=len(inci))
            results["done"] = results.get("done", 0) + 1
            per_brand[brand_dom]["succeeded"] += 1
        else:
            await _save_result(conn, row["queue_id"], row["product_id"], None, "failed")
            log.warning("ingredient_not_found", retailer=slug, url=url)
            results["failed"] = results.get("failed", 0) + 1
            per_brand[brand_dom]["failed"] += 1


async def main() -> None:
    args = _parse_args()

    target_slugs = set(args.retailers) if args.retailers else None

    write_conn = None if args.dry_run else await _get_conn()
    read_conn = write_conn if write_conn else await _get_conn()

    try:
        rows = await _fetch_pending(read_conn, target_slugs, args.limit)
        if not rows:
            log.info("no_pending_entries", target_slugs=sorted(target_slugs) if target_slugs else "all")
            return

        log.info("ingredient_run_start",
                 total=len(rows), dry_run=args.dry_run, concurrency=args.concurrency,
                 retailers=sorted(target_slugs) if target_slugs else "all")

        sem = asyncio.Semaphore(args.concurrency)
        results: dict[str, int] = {}
        per_brand: dict[str, dict] = {}

        strategies = await _load_strategies(read_conn)

        tasks = [
            _worker(sem, row, args.dry_run, write_conn, results, strategies, per_brand)
            for row in rows
        ]
        await asyncio.gather(*tasks)

        log.info("ingredient_run_complete", results=results)

        if not args.dry_run:
            for dom, c in per_brand.items():
                if c["attempted"] == 0:
                    continue
                if c["failed"] == 0:
                    s = "success"
                elif c["succeeded"] == 0:
                    s = "failed"
                else:
                    s = "partial"
                await record_run("ingredient_extract", dom, status=s,
                                 items_attempted=c["attempted"],
                                 items_succeeded=c["succeeded"],
                                 items_failed=c["failed"])

            # Auto-flag strategies with >70% failure rate (min 5 attempts) as needs_review
            # so broken selectors are caught immediately rather than silently failing at scale.
            async with write_conn.cursor() as cur:
                flagged = 0
                for dom, c in per_brand.items():
                    if c["attempted"] < 5:
                        continue
                    fail_rate = c["failed"] / c["attempted"]
                    if fail_rate > 0.70:
                        await cur.execute("""
                            UPDATE scraping.ingredient_strategies
                            SET status = 'needs_review'
                            WHERE brand_domain = %s AND status = 'active'
                        """, (dom,))
                        if cur.rowcount:
                            log.warning("strategy_auto_flagged",
                                        domain=dom, fail_rate=round(fail_rate, 2),
                                        attempted=c["attempted"], failed=c["failed"])
                            flagged += 1
                if flagged:
                    await write_conn.commit()
                    log.info("strategies_flagged_needs_review", count=flagged)

    finally:
        if write_conn:
            await write_conn.close()
        elif read_conn:
            await read_conn.close()


if __name__ == "__main__":
    asyncio.run(main())
