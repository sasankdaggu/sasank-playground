"""
Production scraper entry point.

Usage:
  python -m scraper.run                        # scrape all retailers
  python -m scraper.run --retailers minimalist plum
  python -m scraper.run --tier shopify         # D2C only (no proxy needed)
  python -m scraper.run --tier marketplace
  python -m scraper.run --limit 20             # max products per retailer
  python -m scraper.run --dry-run              # fetch + parse, skip DB writes

For a full weekly catalog refresh (scrape + categorize), use the pipeline:
  python -m scripts.weekly_pipeline

Env vars (from .env or environment):
  DATABASE_URL, SCRAPERAPI_KEY, PROXY_URL, PROXY_USER, PROXY_PASS,
  SCRAPER_HEADLESS (default true), SCRAPER_PAGE_LIMIT (default 2000)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv

# Load .env relative to backend/ root
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app.config import settings  # noqa: E402 (after dotenv load)
from scraper.db import ensure_retailers, fetch_pending_urls, mark_url_done, upsert_product
from scraper.fetchers.catalog import fetch_product_urls_from_catalog, fetch_product_urls_via_httpx
from scraper.fetchers.direct import fetch_pages_direct
from scraper.fetchers.marketplace import fetch_marketplace_pages
from scraper.fetchers.shopify import fetch_shopify_products
from scraper.fetchers.sitemap import fetch_product_urls
from scraper.parsers.marketplace import parse_marketplace_html
from scraper.parsers.shopify import parse_shopify_json
from scraper.parsers.custom_d2c import parse_custom_d2c
from scraper.models import ScrapedProduct
from scraper.retailers import RETAILERS, RetailerTier

log = structlog.get_logger()

# Keywords whose presence in product_type or title indicates a non-face-skincare product.
# Checked on lowercased combined string: "{product_type} {canonical_name}"
_NON_FACE_TOKENS: frozenset[str] = frozenset({
    # Haircare
    "shampoo", "conditioner", "hair oil", "hair mask", "hair serum", "hair cream",
    "hair color", "hair colour", "hair dye", "hair growth", "hair fall", "hair loss",
    "hair repair", "hair shine", "scalp serum", "scalp treatment", "scalp scrub",
    "anti-dandruff", "dandruff", "pre-wash", " scalp ",
    # Body care
    "body wash", "body lotion", "body cream", "body scrub", "body butter",
    "body oil", "body milk", "body mist", "body spray",
    "hand cream", "hand lotion", "hand wash",
    "foot cream", "foot scrub", "foot lotion",
    "shower gel", "shower cream", "bath salt", "bath bomb", "bath & body",
    "bath and body", "bubble bath",
    # Deodorant / fragrance
    "deodorant", "antiperspirant",
    "eau de parfum", "eau de toilette", " edp ", " edt ",
    "perfume", "cologne",
    # Makeup (non-skincare)
    "foundation", " blush", "mascara", "eyeliner", "kajal", "kohl",
    "lipstick", "lip colour", "lip color", "lip liner", "lip gloss",
    "nail polish", "nail lacquer", "nail paint", "nail remover",
    # Non-products / accessories
    "travel pouch", "gift bag", "makeup bag", "sling bag",
    "ice roller", "coffee mug", " pouch", " roller",
    "free surprise", "mystery ",
    # Haircare continued
    "for hair", "hair care", "haircare",
    # Baby / miscellaneous non-face
    "mosquito repellent", "insect repellent", "massage oil", "baby shampoo",
    "baby wash", "baby lotion", "baby oil", "baby cream",
    "foot file", " foot protector", "foot mask",
    "supplement", " gummies", " capsule", " tablet",
})


def _is_face_skincare(product: ScrapedProduct) -> bool:
    """Return True if the product appears to be face skincare.

    Uses exclusion-based matching: products pass unless they contain keywords
    that clearly indicate haircare, body care, makeup, or accessories.
    """
    combined = (
        f" {(product.category_hint or '').lower()} "
        f"{(product.canonical_name or '').lower()} "
    )
    return not any(token in combined for token in _NON_FACE_TOKENS)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wand product scraper")
    parser.add_argument("--retailers", nargs="*", help="Retailer slugs to scrape (default: all)")
    parser.add_argument("--tier", choices=["shopify", "marketplace", "custom"], help="Scrape only one tier")
    parser.add_argument("--limit", type=int, default=settings.scraper_page_limit,
                        help="Max products per retailer")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, skip DB writes")
    return parser.parse_args()


async def _get_conn() -> psycopg.AsyncConnection:
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)


async def run_shopify(retailer, limit: int, dry_run: bool, conn, retailer_ids: dict) -> int:
    assert retailer.products_json_url
    try:
        raw = await fetch_shopify_products(
            retailer.products_json_url, settings.scraperapi_key,
            collection_handle=retailer.collection_handle,
        )
    except Exception as exc:
        log.error("shopify_fetch_error", retailer=retailer.slug, error=str(exc))
        return 0

    all_products = parse_shopify_json(raw, retailer.slug, retailer.base_url)
    products = [p for p in all_products if _is_face_skincare(p)][:limit]
    skipped = len(all_products) - len(products)
    log.info("shopify_parsed", retailer=retailer.slug, total=len(all_products),
             face_skincare=len(products), skipped_non_face=skipped)

    if dry_run:
        return len(products)

    ok = 0
    for p in products:
        try:
            await upsert_product(conn, p, retailer, retailer_ids[retailer.slug])
            ok += 1
        except Exception as exc:
            log.error("upsert_error", retailer=retailer.slug, name=p.canonical_name, error=str(exc))
            await conn.rollback()
    log.info("shopify_done", retailer=retailer.slug, upserted=ok, total=len(products))
    return ok


async def run_marketplace(retailer, limit: int, dry_run: bool, conn, retailer_ids: dict) -> int:
    # URL queue takes priority; fall back to sample_product_urls for dev testing
    url_rows: list[dict] = []
    if conn:
        url_rows = await fetch_pending_urls(conn, retailer_ids[retailer.slug], limit)

    if url_rows:
        urls = [row["url"] for row in url_rows]
        queue_id_by_url = {row["url"]: row["id"] for row in url_rows}
    else:
        urls = list(retailer.sample_product_urls[:limit])
        queue_id_by_url = {}

    if not urls:
        log.warning("no_urls_available", retailer=retailer.slug)
        return 0

    log.info("marketplace_scrape_start", retailer=retailer.slug, urls=len(urls),
             source="queue" if url_rows else "sample")

    pages = await fetch_marketplace_pages(
        urls,
        proxy_url=settings.proxy_url if retailer.needs_proxy else "",
        proxy_user=settings.proxy_user if retailer.needs_proxy else "",
        proxy_pass=settings.proxy_pass if retailer.needs_proxy else "",
        headless=settings.scraper_headless,
    )

    ok = 0
    for url, html, status in pages:
        qid = queue_id_by_url.get(url)
        if not html:
            if qid and conn and not dry_run:
                await mark_url_done(conn, qid, success=False, error_msg=f"http_{status}")
            continue
        p = parse_marketplace_html(html, retailer.slug, url)
        log.info("marketplace_parsed", retailer=retailer.slug, name=p.canonical_name,
                 missing=p.missing_fields)
        if dry_run:
            ok += 1
            continue
        try:
            await upsert_product(conn, p, retailer, retailer_ids[retailer.slug])
            if qid:
                await mark_url_done(conn, qid, success=True)
            ok += 1
        except Exception as exc:
            log.error("upsert_error", retailer=retailer.slug, name=p.canonical_name, error=str(exc))
            await conn.rollback()
            if qid:
                await mark_url_done(conn, qid, success=False, error_msg=str(exc))

    log.info("marketplace_done", retailer=retailer.slug, upserted=ok, total=len(pages))
    return ok


async def run_custom(retailer, limit: int, dry_run: bool, conn, retailer_ids: dict) -> int:
    """Scrape a non-Shopify D2C brand via sitemap (or catalog pages) + HTML parsing."""
    if retailer.catalog_pages and retailer.catalog_link_regex:
        # httpx regex extraction from category pages (e.g. Next.js stores like Olay)
        urls = await fetch_product_urls_via_httpx(
            list(retailer.catalog_pages),
            retailer.catalog_link_regex,
            retailer.base_url,
            limit=limit or 0,
        )
    elif retailer.catalog_pages:
        # Playwright category-page crawler (e.g. Magento 2 stores with no product sitemap)
        urls = await fetch_product_urls_from_catalog(
            list(retailer.catalog_pages),
            headless=settings.scraper_headless,
            limit=limit or 0,
        )
    else:
        assert retailer.sitemap_url and retailer.product_url_pattern
        urls = await fetch_product_urls(
            retailer.sitemap_url,
            retailer.product_url_pattern,
            exclude_patterns=retailer.exclude_url_patterns,
            limit=limit or 0,
            scraperapi_key=settings.scraperapi_key if retailer.needs_proxy else "",
            min_path_depth=retailer.min_path_depth,
        )
    if not urls:
        log.warning("custom_no_urls", retailer=retailer.slug)
        return 0

    log.info("custom_scrape_start", retailer=retailer.slug, urls=len(urls),
             fetch="playwright" if retailer.needs_playwright else "httpx")

    if retailer.needs_playwright:
        pages = await fetch_marketplace_pages(
            urls, proxy_url="", proxy_user="", proxy_pass="",
            headless=settings.scraper_headless,
        )
    else:
        # Most custom D2C brands use server-rendered HTML (JSON-LD, OG tags, __NEXT_DATA__)
        # so httpx is faster and avoids bot-detection that serves JS-only shells to Playwright.
        pages = await fetch_pages_direct(urls)

    all_products = []
    for url, html, status in pages:
        if not html:
            log.warning("custom_fetch_failed", retailer=retailer.slug, url=url, status=status)
            continue
        p = parse_custom_d2c(html, retailer.slug, url)
        all_products.append(p)

    products = [p for p in all_products if _is_face_skincare(p)]
    skipped = len(all_products) - len(products)
    log.info("custom_parsed", retailer=retailer.slug, total=len(all_products),
             face_skincare=len(products), skipped_non_face=skipped)

    if dry_run:
        for p in products[:3]:
            log.info("custom_sample", retailer=retailer.slug, name=p.canonical_name,
                     price=p.current_price, missing=p.missing_fields)
        return len(products)

    ok = 0
    for p in products:
        if not p.canonical_name:
            continue
        try:
            await upsert_product(conn, p, retailer, retailer_ids[retailer.slug])
            ok += 1
        except Exception as exc:
            log.error("upsert_error", retailer=retailer.slug, name=p.canonical_name, error=str(exc))
            await conn.rollback()

    log.info("custom_done", retailer=retailer.slug, upserted=ok, total=len(products))
    return ok


async def main() -> None:
    args = _parse_args()

    retailers = [
        r for r in RETAILERS
        if (not args.retailers or r.slug in args.retailers)
        and (not args.tier or r.tier.value == args.tier)
    ]

    if not retailers:
        log.error("no_matching_retailers")
        sys.exit(1)

    log.info("scrape_start", retailers=[r.slug for r in retailers],
             limit=args.limit, dry_run=args.dry_run)

    conn = await _get_conn() if not args.dry_run else None

    try:
        retailer_ids: dict[str, int] = {}
        if conn:
            retailer_ids = await ensure_retailers(conn)

        total = 0
        for r in retailers:
            if r.tier is RetailerTier.SHOPIFY and r.products_json_url:
                total += await run_shopify(r, args.limit, args.dry_run, conn, retailer_ids)
            elif r.tier is RetailerTier.MARKETPLACE:
                total += await run_marketplace(r, args.limit, args.dry_run, conn, retailer_ids)
            elif r.tier is RetailerTier.CUSTOM:
                total += await run_custom(r, args.limit, args.dry_run, conn, retailer_ids)

        log.info("scrape_complete", total_upserted=total, dry_run=args.dry_run)
    finally:
        if conn:
            await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
