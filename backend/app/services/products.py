from __future__ import annotations

import json

import psycopg

from app.schemas.product import ProductDetail, ProductSearchResult, ProductSummary, RetailerListing


def _base_conditions() -> list[str]:
    """Always-on filters: removes freebies and non-cosmetic items."""
    return [
        "1=1",
        "p.canonical_name NOT ILIKE 'freebie%%'",
        "p.canonical_name NOT ILIKE 'exclusive - %%'",
        "p.canonical_name NOT ILIKE 'exclusive-%%'",
        "p.canonical_name NOT ILIKE '%%swatch%%'",
        "p.canonical_name NOT ILIKE '%% brush%%'",
        "p.canonical_name NOT ILIKE '%%tote bag%%'",
        "p.canonical_name NOT ILIKE '%%hoodie%%'",
        "p.canonical_name NOT ILIKE '%%scrunchie%%'",
        "p.canonical_name NOT ILIKE '%%gua sha%%'",
        "p.canonical_name NOT ILIKE '%%soap saver%%'",
        "p.canonical_name NOT ILIKE '%%pillowcase%%'",
        "p.canonical_name NOT ILIKE '%%gwalsa%%'",
    ]


def _singles_only_conditions() -> list[str]:
    """Extra filters applied when product_type='singles' to hide bundles/packs."""
    return [
        "p.canonical_name NOT ILIKE '%%combo%%'",
        "p.canonical_name NOT ILIKE '%% duo%%'",
        "p.canonical_name NOT ILIKE '%% trio%%'",
        "p.canonical_name NOT ILIKE '%% kit%%'",
        "p.canonical_name NOT ILIKE '%% set'",
        "p.canonical_name NOT ILIKE '%%-pack%%'",
        "p.canonical_name NOT ILIKE '%%pack of%%'",
        "p.canonical_name NOT ILIKE '%%(pack of%%'",
        "p.canonical_name NOT ILIKE '%%bundle%%'",
        "p.canonical_name NOT ILIKE '%%hamper%%'",
        "p.canonical_name NOT ILIKE '%%gift%%'",
        "p.canonical_name NOT ILIKE '%%(free)%%'",
        "p.canonical_name NOT LIKE '%%🎁%%'",
        "p.canonical_name NOT ILIKE '%% off)%%'",
        "p.canonical_name NOT ILIKE '%%-free'",
        "p.canonical_name NOT ILIKE '%% -free'",
        "p.canonical_name NOT ILIKE '%% - free'",
        "p.canonical_name NOT ILIKE 'free - %%'",
        "p.canonical_name NOT ILIKE 'free %%'",
    ]


async def get_filters(
    conn: psycopg.AsyncConnection,
    q: str | None = None,
    brand_ids: list[int] | None = None,
    product_type: str | None = None,
) -> dict:
    conditions = _base_conditions()
    if product_type == "singles":
        conditions.extend(_singles_only_conditions())
    params: list = []

    if q:
        conditions.append("(p.canonical_name %% %s OR b.name ILIKE %s OR p.ingredients_raw ILIKE %s)")
        params.extend([q, f"%{q}%", f"%{q}%"])
    if brand_ids:
        placeholders = ",".join(["%s"] * len(brand_ids))
        conditions.append(f"p.brand_id IN ({placeholders})")
        params.extend(brand_ids)

    where = " AND ".join(conditions)

    # Brands with at least one matching product
    brand_sql = f"""
        SELECT DISTINCT b.id, b.name
        FROM core.products p
        JOIN core.brands b ON b.id = p.brand_id
        LEFT JOIN taxonomy.categories tc ON tc.id = p.canonical_category_id
        WHERE {where}
        ORDER BY b.name
    """
    # Subcategories used by matching products + their parent categories
    cat_sql = f"""
        WITH matched_cats AS (
            SELECT DISTINCT tc.id, tc.name, tc.slug, tc.parent_id
            FROM core.products p
            JOIN core.brands b ON b.id = p.brand_id
            JOIN taxonomy.categories tc ON tc.id = p.canonical_category_id
            WHERE {where}
        )
        SELECT * FROM matched_cats
        UNION
        SELECT p.id, p.name, p.slug, p.parent_id
        FROM taxonomy.categories p
        WHERE p.id IN (SELECT parent_id FROM matched_cats WHERE parent_id IS NOT NULL)
        ORDER BY parent_id NULLS FIRST, name
    """

    async with conn.cursor() as cur:
        await cur.execute(brand_sql, params)
        brand_rows = await cur.fetchall()

    async with conn.cursor() as cur:
        await cur.execute(cat_sql, params)
        cat_rows = await cur.fetchall()

    brands = [{"id": r["id"], "name": r["name"]} for r in brand_rows]
    categories = [
        {"id": r["id"], "name": r["name"], "slug": r["slug"], "parent_id": r["parent_id"]}
        for r in cat_rows
    ]
    return {"brands": brands, "categories": categories}


async def search_products(
    conn: psycopg.AsyncConnection,
    q: str | None,
    category: str | None,
    brand_ids: list[int],
    product_type: str | None,
    page: int,
    page_size: int,
) -> ProductSearchResult:
    offset = (page - 1) * page_size
    conditions = _base_conditions()
    if product_type == "singles":
        conditions.extend(_singles_only_conditions())
    params: list = []

    if q:
        conditions.append("(p.canonical_name %% %s OR b.name ILIKE %s OR p.ingredients_raw ILIKE %s)")
        params.extend([q, f"%{q}%", f"%{q}%"])
    if brand_ids:
        placeholders = ",".join(["%s"] * len(brand_ids))
        conditions.append(f"p.brand_id IN ({placeholders})")
        params.extend(brand_ids)
    if category:
        conditions.append("(tc.slug = %s OR parent_tc.slug = %s)")
        params.extend([category, category])

    where = " AND ".join(conditions)

    count_sql = f"""
        SELECT count(*) FROM core.products p
        JOIN core.brands b ON b.id = p.brand_id
        LEFT JOIN taxonomy.categories tc ON tc.id = p.canonical_category_id
        LEFT JOIN taxonomy.categories parent_tc ON parent_tc.id = tc.parent_id
        WHERE {where}
    """
    async with conn.cursor() as cur:
        await cur.execute(count_sql, params)
        total = (await cur.fetchone())["count"]

    list_sql = f"""
        SELECT
            p.id,
            p.canonical_name,
            b.name AS brand_name,
            p.images,
            p.ingredient_scrape_status,
            min(rl.current_price) AS min_price,
            max(rl.current_price) AS max_price,
            count(DISTINCT rl.retailer_id) AS retailer_count
        FROM core.products p
        JOIN core.brands b ON b.id = p.brand_id
        LEFT JOIN core.retailer_listings rl ON rl.product_id = p.id
        LEFT JOIN taxonomy.categories tc ON tc.id = p.canonical_category_id
        LEFT JOIN taxonomy.categories parent_tc ON parent_tc.id = tc.parent_id
        WHERE {where}
        GROUP BY p.id, b.name
        ORDER BY p.id
        LIMIT %s OFFSET %s
    """
    async with conn.cursor() as cur:
        await cur.execute(list_sql, params + [page_size, offset])
        rows = await cur.fetchall()

    items = [
        ProductSummary(
            id=r["id"],
            canonical_name=r["canonical_name"],
            brand_name=r["brand_name"],
            images=r["images"] if isinstance(r["images"], list) else json.loads(r["images"] or "[]"),
            min_price=r["min_price"],
            max_price=r["max_price"],
            retailer_count=r["retailer_count"],
            ingredient_scrape_status=r["ingredient_scrape_status"],
        )
        for r in rows
    ]
    return ProductSearchResult(items=items, total=total, page=page, page_size=page_size)


async def get_product(conn: psycopg.AsyncConnection, product_id: int) -> ProductDetail | None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT
                p.id, p.canonical_name, p.brand_id, p.images, p.variants,
                p.description_raw, p.description_source, p.ingredient_scrape_status,
                p.ingredients_raw,
                b.name AS brand_name,
                tc.name AS category_name
            FROM core.products p
            JOIN core.brands b ON b.id = p.brand_id
            LEFT JOIN taxonomy.categories tc ON tc.id = p.canonical_category_id
            WHERE p.id = %s
            """,
            (product_id,),
        )
        row = await cur.fetchone()

    if not row:
        return None

    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT
                rl.retailer_id, r.name AS retailer_name, r.slug AS retailer_slug,
                rl.listing_url, rl.current_price, rl.compare_at_price,
                rl.stock_status, rl.rating_value, rl.rating_count,
                rl.last_scraped_at
            FROM core.retailer_listings rl
            JOIN core.retailers r ON r.id = rl.retailer_id
            WHERE rl.product_id = %s
            ORDER BY rl.current_price ASC NULLS LAST
            """,
            (product_id,),
        )
        listing_rows = await cur.fetchall()

    listings = [
        RetailerListing(
            retailer_id=lr["retailer_id"],
            retailer_name=lr["retailer_name"],
            retailer_slug=lr["retailer_slug"],
            listing_url=lr["listing_url"],
            current_price=lr["current_price"],
            compare_at_price=lr["compare_at_price"],
            stock_status=lr["stock_status"],
            rating_value=lr["rating_value"],
            rating_count=lr["rating_count"],
            last_scraped_at=str(lr["last_scraped_at"]) if lr["last_scraped_at"] else None,
        )
        for lr in listing_rows
    ]

    images = row["images"]
    if not isinstance(images, list):
        images = json.loads(images or "[]")
    variants = row["variants"]
    if not isinstance(variants, list):
        variants = json.loads(variants or "[]")

    return ProductDetail(
        id=row["id"],
        canonical_name=row["canonical_name"],
        brand_name=row["brand_name"],
        brand_id=row["brand_id"],
        images=images,
        variants=variants,
        description_raw=row["description_raw"],
        description_source=row["description_source"],
        ingredient_scrape_status=row["ingredient_scrape_status"],
        ingredients_raw=row["ingredients_raw"],
        listings=listings,
        category=row["category_name"],
    )
