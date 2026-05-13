"""
Scrape Shopify collection pages for all D2C brands and use them to fill in
category_raw for products that currently have NULL category_raw.

For each Shopify brand:
  1. Hit {base_url}/collections.json?limit=250&page=N until empty
  2. Filter out non-product collections (frontpage, home, sale, new, best,
     featured, all, hidden) by handle
  3. For each remaining collection, hit /collections/{handle}/products.json
     and collect all product handles
  4. For each product handle, look up core.retailer_listings.listing_url
     containing /products/{handle} — if found and category_raw IS NULL,
     set category_raw = collection.title

Usage:
    .venv/bin/python scripts/scrape_collection_signals.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

import aiohttp
import psycopg
import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

log = structlog.get_logger()

# ── Handles that indicate non-product-category collections ────────────────────
SKIP_HANDLE_SUBSTRINGS = frozenset({
    "frontpage", "home-page", "homepage",
    "sale", "clearance", "offers",
    "new-arrivals", "new-in", "new-launch",
    "best-seller", "best-sellers", "bestseller", "bestsellers",
    "featured", "features",
    "all", "shop-all", "all-products",
    "hidden",
    "gift", "gifts", "gift-set",
    "bundle", "bundles",
    "kit", "kits",
    "sample", "samples", "free-sample",
    "combo", "combos",
    "test", "draft",
})

# Also skip handles that are exactly these tokens (to catch short slugs)
SKIP_HANDLE_EXACT = frozenset({
    "all", "frontpage", "home", "sale", "new", "best",
    "featured", "hidden", "face", "body", "hair",
})

# Concurrency limit — max simultaneous HTTP requests per brand
CONCURRENCY = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

TIMEOUT = aiohttp.ClientTimeout(total=30)


class CollectionInfo(NamedTuple):
    handle: str
    title: str


def _should_skip_handle(handle: str) -> bool:
    """Return True if this collection handle looks like a non-category collection."""
    h = handle.lower()
    if h in SKIP_HANDLE_EXACT:
        return True
    for sub in SKIP_HANDLE_SUBSTRINGS:
        if sub in h:
            return True
    return False


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict | list | None:
    """Fetch a URL and return parsed JSON, or None on error."""
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT, ssl=False) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
            elif resp.status == 404:
                return None
            else:
                log.warning("http_error", url=url, status=resp.status)
                return None
    except Exception as exc:
        log.warning("fetch_error", url=url, error=str(exc))
        return None


async def _get_collections(session: aiohttp.ClientSession, base_url: str) -> list[CollectionInfo]:
    """Fetch all collections for a Shopify brand, filtering out non-category ones."""
    collections: list[CollectionInfo] = []
    page = 1
    while True:
        url = f"{base_url}/collections.json?limit=250&page={page}"
        data = await _fetch_json(session, url)
        if not data or not isinstance(data, dict):
            break
        items = data.get("collections", [])
        if not items:
            break
        for c in items:
            handle = c.get("handle", "")
            title = c.get("title", "")
            if not handle or not title:
                continue
            if _should_skip_handle(handle):
                continue
            collections.append(CollectionInfo(handle=handle, title=title))
        if len(items) < 250:
            break
        page += 1
    return collections


async def _get_collection_product_handles(
    session: aiohttp.ClientSession,
    base_url: str,
    collection_handle: str,
    semaphore: asyncio.Semaphore,
) -> list[str]:
    """Fetch all product handles in a collection (paginated)."""
    handles: list[str] = []
    page = 1
    while True:
        url = f"{base_url}/collections/{collection_handle}/products.json?limit=250&page={page}"
        async with semaphore:
            data = await _fetch_json(session, url)
        if not data or not isinstance(data, dict):
            break
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            h = p.get("handle", "")
            if h:
                handles.append(h)
        if len(products) < 250:
            break
        page += 1
    return handles


async def _get_db_conn() -> psycopg.AsyncConnection:
    dsn = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)


async def process_brand(
    session: aiohttp.ClientSession,
    conn: psycopg.AsyncConnection,
    slug: str,
    base_url: str,
    retailer_id: int,
) -> int:
    """Process one brand: scrape collections and update category_raw. Returns update count."""
    print(f"\n  [{slug}] Fetching collections from {base_url}/collections.json ...")
    collections = await _get_collections(session, base_url)
    if not collections:
        print(f"  [{slug}] No product collections found (or all filtered out) — skipping.")
        return 0

    print(f"  [{slug}] Found {len(collections)} product collections: "
          f"{', '.join(c.handle for c in collections[:5])}"
          + (" ..." if len(collections) > 5 else ""))

    # Semaphore to limit concurrent requests per brand
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # Fetch all collection→product mappings concurrently
    tasks = [
        _get_collection_product_handles(session, base_url, c.handle, semaphore)
        for c in collections
    ]
    results = await asyncio.gather(*tasks)

    # Build handle → first-seen collection title mapping
    # (first collection wins if a product appears in multiple)
    handle_to_category: dict[str, str] = {}
    for collection, handles in zip(collections, results):
        for h in handles:
            if h not in handle_to_category:
                handle_to_category[h] = collection.title

    if not handle_to_category:
        print(f"  [{slug}] No product handles found across collections.")
        return 0

    print(f"  [{slug}] Mapped {len(handle_to_category)} unique product handles across "
          f"{len(collections)} collections.")

    # Look up products in DB via retailer_listings.listing_url
    # listing_url format: {base_url}/products/{handle}
    # We match by: listing_url LIKE '%/products/{handle}' AND retailer_id = {retailer_id}
    # Then update core.products.category_raw where IS NULL
    updated = 0
    async with conn.cursor() as cur:
        for handle, category_title in handle_to_category.items():
            listing_pattern = f"%/products/{handle}"
            await cur.execute(
                """
                UPDATE core.products p
                SET    category_raw = %s
                FROM   core.retailer_listings rl
                WHERE  rl.product_id = p.id
                  AND  rl.retailer_id = %s
                  AND  rl.listing_url LIKE %s
                  AND  p.category_raw IS NULL
                """,
                (category_title, retailer_id, listing_pattern),
            )
            updated += cur.rowcount

    await conn.commit()
    print(f"  [{slug}] Updated category_raw for {updated} products.")
    return updated


async def main() -> None:
    # Import retailers definition
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scraper.retailers import RETAILERS, RetailerTier

    # Get Shopify D2C brands only
    shopify_brands = [r for r in RETAILERS if r.tier == RetailerTier.SHOPIFY]
    print(f"Found {len(shopify_brands)} Shopify D2C brands to process.")

    # Connect to DB
    conn = await _get_db_conn()

    # Get baseline count
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) as cnt FROM core.products WHERE category_raw IS NULL"
        )
        before_null = (await cur.fetchone())["cnt"]
        await cur.execute(
            "SELECT COUNT(*) as cnt FROM core.products WHERE canonical_category_id IS NOT NULL"
        )
        before_categorized = (await cur.fetchone())["cnt"]

    print(f"\nBaseline: {before_null} products with NULL category_raw")
    print(f"Baseline: {before_categorized} products with canonical_category_id set")

    # Build slug → retailer_id map from DB
    async with conn.cursor() as cur:
        await cur.execute("SELECT id, slug FROM core.retailers")
        db_retailers = {r["slug"]: r["id"] for r in await cur.fetchall()}

    total_updated = 0

    async with aiohttp.ClientSession() as session:
        for brand in shopify_brands:
            retailer_id = db_retailers.get(brand.slug)
            if retailer_id is None:
                print(f"\n  [{brand.slug}] NOT FOUND in DB — skipping.")
                continue
            try:
                n = await process_brand(session, conn, brand.slug, brand.base_url, retailer_id)
                total_updated += n
            except Exception as exc:
                print(f"\n  [{brand.slug}] ERROR: {exc}")
                log.exception("brand_error", slug=brand.slug, error=str(exc))

    # Final count
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) as cnt FROM core.products WHERE category_raw IS NULL"
        )
        after_null = (await cur.fetchone())["cnt"]

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Products with NULL category_raw BEFORE: {before_null}")
    print(f"  Products with NULL category_raw AFTER:  {after_null}")
    print(f"  Products that got category_raw filled:  {before_null - after_null}")
    print(f"  Total DB updates committed:             {total_updated}")
    print(f"{'='*60}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
