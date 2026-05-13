"""Async DB operations for the scraper — upserts into production schema."""
from __future__ import annotations

import json
import re

import psycopg
import structlog

from scraper.models import ScrapedProduct
from scraper.retailers import RETAILERS, Retailer

log = structlog.get_logger()


async def ensure_retailers(conn: psycopg.AsyncConnection) -> dict[str, int]:
    """Upsert all retailers; return slug→id map."""
    slug_to_id: dict[str, int] = {}
    async with conn.cursor() as cur:
        for r in RETAILERS:
            await cur.execute(
                """
                INSERT INTO core.retailers (slug, name, base_url, needs_proxy, is_authoritative_for_catalog)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET
                  name = EXCLUDED.name,
                  base_url = EXCLUDED.base_url,
                  needs_proxy = EXCLUDED.needs_proxy,
                  is_authoritative_for_catalog = EXCLUDED.is_authoritative_for_catalog
                RETURNING id
                """,
                (r.slug, r.name, r.base_url, r.needs_proxy, r.is_authoritative_for_catalog),
            )
            row = await cur.fetchone()
            slug_to_id[r.slug] = row["id"]
    await conn.commit()
    log.info("retailers_synced", count=len(slug_to_id))
    return slug_to_id


async def upsert_product(
    conn: psycopg.AsyncConnection,
    product: ScrapedProduct,
    retailer: Retailer,
    retailer_id: int,
) -> None:
    """Upsert brand, product, listing, and ingredient queue entry."""
    if not product.canonical_name:
        log.warning("skipping_nameless_product", retailer=product.retailer_slug, url=product.source_url)
        return

    async with conn.cursor() as cur:
        # Brand — upsert by name
        brand_name = product.brand_name or retailer.name
        await cur.execute(
            "INSERT INTO core.brands (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
            (brand_name,),
        )
        brand_id = (await cur.fetchone())["id"]

        variants_json = json.dumps([
            {"sku": v.sku, "option_value": v.option_value, "price": v.price,
             "compare_at_price": v.compare_at_price, "available": v.available}
            for v in product.variants
        ])
        images_json = json.dumps(product.images or [])
        skin_type_json = json.dumps(product.skin_type) if product.skin_type else None
        skin_concerns_json = json.dumps(product.skin_concerns) if product.skin_concerns else None
        claims_json = json.dumps(product.claims) if product.claims else None
        source_tags_json = json.dumps(product.source_tags) if product.source_tags else None

        # Non-authoritative retailers (Amazon): only create a listing if product already exists
        if not retailer.can_create_canonical:
            await cur.execute(
                "SELECT id FROM core.products WHERE brand_id = %s AND canonical_name = %s",
                (brand_id, product.canonical_name),
            )
            existing = await cur.fetchone()
            if not existing:
                log.info("skip_non_canonical_new_product", retailer=retailer.slug, name=product.canonical_name)
                return
            product_id = existing["id"]
        else:
            # Upsert product — higher-priority source (lower image_priority number) wins.
            # COALESCE(CASE WHEN priority_wins THEN new_val END, old_val) means:
            # "use new_val if we win priority AND it's not NULL, else keep old"
            await cur.execute(
                """
                INSERT INTO core.products
                  (brand_id, canonical_name, variants, images, image_priority,
                   description_raw, description_source, ingredient_scrape_status,
                   ingredients_raw,
                   category_raw, subcategory_raw, pack_size, how_to_use,
                   skin_type, skin_concerns, country_of_origin,
                   key_ingredients_raw, claims, source_tags)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, 'pending',
                        %s,
                        %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s,
                        %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (brand_id, canonical_name) DO UPDATE SET
                  images = CASE
                    WHEN EXCLUDED.image_priority <= core.products.image_priority
                    THEN EXCLUDED.images ELSE core.products.images END,
                  variants = CASE
                    WHEN EXCLUDED.image_priority <= core.products.image_priority
                    THEN EXCLUDED.variants ELSE core.products.variants END,
                  description_raw = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.description_raw END,
                    core.products.description_raw),
                  description_source = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                         AND EXCLUDED.description_raw IS NOT NULL
                      THEN EXCLUDED.description_source END,
                    core.products.description_source),
                  ingredients_raw = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.ingredients_raw END,
                    core.products.ingredients_raw),
                  category_raw = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.category_raw END,
                    core.products.category_raw),
                  subcategory_raw = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.subcategory_raw END,
                    core.products.subcategory_raw),
                  pack_size = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.pack_size END,
                    core.products.pack_size),
                  how_to_use = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.how_to_use END,
                    core.products.how_to_use),
                  skin_type = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.skin_type END,
                    core.products.skin_type),
                  skin_concerns = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.skin_concerns END,
                    core.products.skin_concerns),
                  country_of_origin = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.country_of_origin END,
                    core.products.country_of_origin),
                  key_ingredients_raw = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.key_ingredients_raw END,
                    core.products.key_ingredients_raw),
                  claims = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.claims END,
                    core.products.claims),
                  source_tags = COALESCE(
                    CASE WHEN EXCLUDED.image_priority <= core.products.image_priority
                      THEN EXCLUDED.source_tags END,
                    core.products.source_tags),
                  image_priority = LEAST(EXCLUDED.image_priority, core.products.image_priority)
                RETURNING id
                """,
                (
                    brand_id, product.canonical_name, variants_json, images_json,
                    retailer.image_priority, product.description_raw, product.description_source,
                    product.ingredients_raw,
                    product.category_hint, product.subcategory_hint, product.pack_size, product.how_to_use,
                    skin_type_json, skin_concerns_json, product.country_of_origin,
                    product.key_ingredients_raw, claims_json, source_tags_json,
                ),
            )
            product_id = (await cur.fetchone())["id"]

        # Retailer listing — upsert price + stock on conflict
        stock_status = _normalize_stock(product.stock_status_raw)
        await cur.execute(
            """
            INSERT INTO core.retailer_listings
              (product_id, retailer_id, listing_url, current_price, compare_at_price,
               stock_status, stock_status_raw, rating_value, rating_count, rating_raw,
               last_scraped_at)
            VALUES (%s, %s, %s, %s, %s, %s::core.stock_status_enum, %s, %s, %s, %s, now())
            ON CONFLICT (product_id, retailer_id) DO UPDATE SET
              listing_url = EXCLUDED.listing_url,
              current_price = EXCLUDED.current_price,
              compare_at_price = EXCLUDED.compare_at_price,
              stock_status = EXCLUDED.stock_status,
              stock_status_raw = EXCLUDED.stock_status_raw,
              rating_value = COALESCE(EXCLUDED.rating_value, core.retailer_listings.rating_value),
              rating_count = COALESCE(EXCLUDED.rating_count, core.retailer_listings.rating_count),
              rating_raw = COALESCE(EXCLUDED.rating_raw, core.retailer_listings.rating_raw),
              last_scraped_at = now()
            RETURNING id
            """,
            (
                product_id, retailer_id, product.source_url,
                product.current_price, product.compare_at_price,
                stock_status, product.stock_status_raw,
                _parse_rating_value(product.rating_raw),
                _parse_rating_count(product.rating_raw),
                product.rating_raw,
            ),
        )
        listing_id = (await cur.fetchone())["id"]

        # Ingredient queue — only insert if not already queued
        await cur.execute(
            """
            INSERT INTO scraping.ingredient_extraction_queue (product_id, listing_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (product_id, listing_id),
        )

    await conn.commit()


async def queue_discovered_urls(
    conn: psycopg.AsyncConnection,
    retailer_id: int,
    urls: list[str],
    category_hint: str,
) -> int:
    """Batch-insert discovered URLs; skip duplicates. Returns count of newly inserted rows."""
    if not urls:
        return 0
    async with conn.cursor() as cur:
        await cur.executemany(
            """
            INSERT INTO scraping.url_queue (retailer_id, url, category_hint)
            VALUES (%s, %s, %s)
            ON CONFLICT (retailer_id, url) DO NOTHING
            """,
            [(retailer_id, url, category_hint) for url in urls],
        )
        inserted = cur.rowcount if cur.rowcount >= 0 else 0
    await conn.commit()
    return inserted


async def fetch_pending_urls(
    conn: psycopg.AsyncConnection,
    retailer_id: int,
    limit: int = 100,
) -> list[dict]:
    """Return up to `limit` pending URLs for a retailer, oldest-first."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT id, url, category_hint
            FROM scraping.url_queue
            WHERE retailer_id = %s AND status = 'pending'
            ORDER BY discovered_at
            LIMIT %s
            """,
            (retailer_id, limit),
        )
        return await cur.fetchall()


async def mark_url_done(
    conn: psycopg.AsyncConnection,
    queue_id: int,
    *,
    success: bool,
    error_msg: str | None = None,
) -> None:
    """Mark a queued URL as scraped or failed."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE scraping.url_queue
            SET status = %s, scraped_at = now(), attempts = attempts + 1, error_msg = %s
            WHERE id = %s
            """,
            ("scraped" if success else "failed", error_msg, queue_id),
        )
    await conn.commit()


def _normalize_stock(raw: str | None) -> str:
    if not raw:
        return "unknown"
    s = raw.lower()
    if "out" in s or "unavailable" in s:
        return "out_of_stock"
    if "low" in s:
        return "low_stock"
    if "in" in s or "stock" in s:
        return "in_stock"
    return "unknown"


def _parse_rating_value(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.split()[0])
    except (ValueError, IndexError):
        return None


def _parse_rating_count(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r'\((\d+)\)', raw)
    return int(m.group(1)) if m else None
