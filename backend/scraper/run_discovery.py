"""
Marketplace URL discovery — crawls Nykaa, Tira, and Purplle product sitemaps
to discover face skincare products and queue their URLs for scraping.

Sitemaps are static XML (no JS rendering needed), making discovery reliable
and fast compared to scraping category listing pages.

Usage:
  python -m scraper.run_discovery                          # all marketplaces
  python -m scraper.run_discovery --retailers nykaa        # one marketplace
  python -m scraper.run_discovery --max-sitemaps 5         # limit sitemaps per retailer (dev/test)
  python -m scraper.run_discovery --dry-run                # count only, no DB writes

Then process the queue:
  python -m scraper.run --tier marketplace --limit 500
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app.config import settings  # noqa: E402
from scraper.db import ensure_retailers, queue_discovered_urls
from scraper.discovery.sitemaps import FACE_SKINCARE_SOURCES, discover_from_sitemaps

log = structlog.get_logger()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Marketplace product URL discovery via sitemaps")
    parser.add_argument("--retailers", nargs="*", help="Retailer slugs to discover (default: all)")
    parser.add_argument("--max-sitemaps", type=int, default=0,
                        help="Max sub-sitemaps per retailer (0=all, useful for dev)")
    parser.add_argument("--dry-run", action="store_true", help="Count URLs without DB writes")
    return parser.parse_args()


async def _get_conn() -> psycopg.AsyncConnection:
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)


async def main() -> None:
    args = _parse_args()

    sources = [
        s for s in FACE_SKINCARE_SOURCES
        if not args.retailers or s.retailer_slug in args.retailers
    ]
    if not sources:
        log.error("no_matching_retailers")
        return

    if not settings.scraperapi_key:
        log.error("scraperapi_key_required",
                  msg="Set SCRAPERAPI_KEY in .env — needed to fetch sitemaps via India IP")
        return

    log.info("discovery_start",
             retailers=[s.retailer_slug for s in sources],
             max_sitemaps=args.max_sitemaps or "all",
             dry_run=args.dry_run)

    conn = await _get_conn() if not args.dry_run else None

    try:
        retailer_ids: dict[str, int] = {}
        if conn:
            retailer_ids = await ensure_retailers(conn)

        totals: dict[str, int] = {}

        for source in sources:
            url_hints = await discover_from_sitemaps(
                source,
                scraperapi_key=settings.scraperapi_key,
                max_sitemaps=args.max_sitemaps,
            )

            if not args.dry_run and url_hints and conn:
                # Group by hint for batch insert
                by_hint: dict[str, list[str]] = {}
                for url, hint in url_hints:
                    by_hint.setdefault(hint, []).append(url)

                inserted_total = 0
                for hint, urls in by_hint.items():
                    inserted = await queue_discovered_urls(
                        conn, retailer_ids[source.retailer_slug], urls, hint
                    )
                    inserted_total += inserted

                log.info("discovery_queued",
                         retailer=source.retailer_slug,
                         found=len(url_hints), new=inserted_total)
                totals[source.retailer_slug] = inserted_total
            else:
                log.info("discovery_dry_run",
                         retailer=source.retailer_slug, found=len(url_hints))
                totals[source.retailer_slug] = len(url_hints)

        log.info("discovery_complete", totals=totals, dry_run=args.dry_run)

    finally:
        if conn:
            await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
