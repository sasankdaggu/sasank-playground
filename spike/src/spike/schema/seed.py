"""Load parsed spike samples into v1 schema and verify canonical queries.

Requires a running Postgres instance (docker compose up -d from repo root).
DATABASE_URL defaults to postgresql://wand:wand@localhost:5433/wand_spike
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
import structlog

from spike.config import retailer_by_slug
from spike.models import ParsedSample

log = structlog.get_logger()

SPIKE_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # spike/


def _conn() -> psycopg.Connection:
    url = os.getenv("DATABASE_URL", "postgresql://wand:wand@localhost:5433/wand_spike")
    dsn = url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(dsn)


def load_schema(conn: psycopg.Connection, sql_path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS core CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS users CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS scraping CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS taxonomy CASCADE")
        cur.execute(sql_path.read_text())
    conn.commit()
    log.info("schema_loaded", path=str(sql_path))


def seed_retailers(conn: psycopg.Connection) -> dict[str, int]:
    """Insert all 7 spike retailers, return slug→id map."""
    retailers = [
        ("minimalist",    "Minimalist",    "https://beminimalist.co",      False, True),
        ("plum",          "Plum Goodness", "https://plumgoodness.com",     False, True),
        ("mcaffeine",     "mCaffeine",     "https://mcaffeine.com",        False, True),
        ("dot_and_key",   "Dot & Key",     "https://dotandkey.com",        False, True),
        ("the_derma_co",  "The Derma Co",  "https://thedermaco.com",       False, True),
        ("tira",          "Tira",          "https://www.tirabeauty.com",   True,  False),
        ("purplle",       "Purplle",       "https://www.purplle.com",      True,  False),
    ]
    slug_to_id: dict[str, int] = {}
    with conn.cursor() as cur:
        for slug, name, base_url, needs_proxy, is_auth in retailers:
            cur.execute(
                """
                INSERT INTO core.retailers (slug, name, base_url, needs_proxy, is_authoritative_for_catalog)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (slug, name, base_url, needs_proxy, is_auth),
            )
            slug_to_id[slug] = cur.fetchone()[0]
    conn.commit()
    log.info("retailers_seeded", count=len(slug_to_id))
    return slug_to_id


def seed_sample(
    conn: psycopg.Connection,
    ps: ParsedSample,
    retailer_ids: dict[str, int],
) -> None:
    """Insert one ParsedSample into v1 schema."""
    retailer_id = retailer_ids.get(ps.retailer_slug)
    if retailer_id is None:
        log.warning("unknown_retailer", slug=ps.retailer_slug)
        return

    if ps.canonical_name is None:
        log.warning("skipping_nameless_sample", url=ps.source_url)
        return

    try:
        retailer_cfg = retailer_by_slug(ps.retailer_slug)
    except KeyError:
        retailer_cfg = None

    with conn.cursor() as cur:
        # Brand — upsert by name.
        brand_name = ps.brand_name or ps.retailer_slug
        cur.execute(
            "INSERT INTO core.brands (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
            (brand_name,),
        )
        brand_id = cur.fetchone()[0]

        image_priority = retailer_cfg.image_priority if retailer_cfg else 99
        catalog_priority = retailer_cfg.catalog_priority if retailer_cfg else 99
        can_create = retailer_cfg.can_create_canonical if retailer_cfg else True

        # Product — insert (allow duplicates across retailers for the spike).
        stock_status = "unknown"
        if ps.stock_status_raw:
            s = ps.stock_status_raw.lower()
            if "out" in s or "unavailable" in s:
                stock_status = "out_of_stock"
            elif "low" in s:
                stock_status = "low_stock"
            else:
                stock_status = "in_stock"

        variants_json = "[" + ",".join(v.model_dump_json() for v in ps.variants) + "]"
        import json as _json
        images_json = _json.dumps(ps.images or [])

        # Amazon and other non-canonical retailers: only add a listing, never create a product.
        if not can_create:
            cur.execute(
                "SELECT id FROM core.products WHERE brand_id = %s AND canonical_name = %s",
                (brand_id, ps.canonical_name),
            )
            existing = cur.fetchone()
            if not existing:
                log.info("skipping_non_canonical_new_product",
                         retailer=ps.retailer_slug, name=ps.canonical_name)
                return
            product_id = existing[0]
        else:
            cur.execute(
                """
                INSERT INTO core.products
                  (brand_id, canonical_name, variants, images, image_priority,
                   description_raw, description_source, ingredient_scrape_status)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, 'pending')
                ON CONFLICT (brand_id, canonical_name) DO UPDATE SET
                  -- Higher-priority source (lower number) wins on all canonical fields
                  images = CASE
                    WHEN EXCLUDED.image_priority <= core.products.image_priority
                    THEN EXCLUDED.images ELSE core.products.images
                  END,
                  variants = CASE
                    WHEN EXCLUDED.image_priority <= core.products.image_priority
                    THEN EXCLUDED.variants ELSE core.products.variants
                  END,
                  description_raw = CASE
                    WHEN EXCLUDED.image_priority <= core.products.image_priority
                      AND EXCLUDED.description_raw IS NOT NULL
                    THEN EXCLUDED.description_raw ELSE core.products.description_raw
                  END,
                  description_source = CASE
                    WHEN EXCLUDED.image_priority <= core.products.image_priority
                      AND EXCLUDED.description_raw IS NOT NULL
                    THEN EXCLUDED.description_source ELSE core.products.description_source
                  END,
                  image_priority = LEAST(EXCLUDED.image_priority, core.products.image_priority)
                RETURNING id
                """,
                (
                    brand_id,
                    ps.canonical_name,
                    variants_json,
                    images_json,
                    image_priority,
                    ps.description_raw,
                    "shopify_body_html" if ps.retailer_slug not in ("tira", "purplle") else "product_page_scrape",
                ),
            )
            product_id = cur.fetchone()[0]

        # Retailer listing.
        cur.execute(
            """
            INSERT INTO core.retailer_listings
              (product_id, retailer_id, listing_url, current_price, compare_at_price,
               stock_status, stock_status_raw, rating_value, rating_count, rating_raw)
            VALUES (%s, %s, %s, %s, %s, %s::core.stock_status_enum, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                product_id,
                retailer_id,
                ps.source_url,
                ps.current_price,
                ps.compare_at_price,
                stock_status,
                ps.stock_status_raw,
                _parse_rating_value(ps.rating_raw),
                _parse_rating_count(ps.rating_raw),
                ps.rating_raw,
            ),
        )
        listing_id = cur.fetchone()[0]

        # Ingredient extraction queue — every product starts pending.
        cur.execute(
            "INSERT INTO scraping.ingredient_extraction_queue (product_id, listing_id) VALUES (%s, %s)",
            (product_id, listing_id),
        )
    conn.commit()


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
    import re
    m = re.search(r'\((\d+)\)', raw)
    return int(m.group(1)) if m else None


def load_all_samples(parsed_dir: Path) -> list[ParsedSample]:
    samples = []
    for p in sorted(parsed_dir.glob("*/*.json")):
        samples.append(ParsedSample.model_validate_json(p.read_text()))
    return samples


def verify_queries(conn: psycopg.Connection) -> None:
    """Run the 3 canonical Phase 1 queries and log results."""
    with conn.cursor() as cur:
        # 1. Price compare: cheapest listing per product.
        cur.execute("""
            SELECT p.canonical_name, min(rl.current_price) as min_price
              FROM core.products p
              JOIN core.retailer_listings rl ON rl.product_id = p.id
             WHERE rl.current_price IS NOT NULL
             GROUP BY p.id, p.canonical_name
             ORDER BY min_price
             LIMIT 5
        """)
        log.info("query_price_compare", results=cur.fetchall())

        # 2. Shelf read: all products for a user (seeded with first user).
        cur.execute("SELECT id FROM users.users LIMIT 1")
        row = cur.fetchone()
        if row:
            cur.execute("""
                SELECT p.canonical_name FROM users.shelf_items si
                  JOIN core.products p ON p.id = si.product_id
                 WHERE si.user_id = %s
            """, (row[0],))
            log.info("query_shelf_read", results=cur.fetchall())

        # 3. Search: trigram search for "niacinamide".
        cur.execute(
            "SELECT canonical_name FROM core.products WHERE canonical_name %% %s LIMIT 5",
            ("niacinamide",),
        )
        log.info("query_search_trgm", results=cur.fetchall())

        # 4. Ingredient queue depth.
        cur.execute("SELECT count(*) FROM scraping.ingredient_extraction_queue WHERE status = 'pending'")
        log.info("ingredient_queue_depth", pending=cur.fetchone()[0])
