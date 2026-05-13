"""
Scrape breadcrumb / category navigation from non-Shopify brand product pages
and back-fill core.products.category_raw where currently NULL.

Extraction strategies (tried in order per brand):
  1. JSON-LD BreadcrumbList  — Mamaearth, CeraVe, Olay (≥3 items only)
  2. URL-path segment        — Neutrogena (/face/{category}/), Cetaphil (/product-range/{category}/)
  3. NEXT_DATA / Apollo JSON — The Body Shop (productDetailReducer),
                               Plix (search_product_type metadata),
                               Kama Ayurveda (initialApolloState CategoryTree / pdp.categories)
  4. dataLayer GA ecommerce  — Forest Essentials (ecommerce.detail.products.category)
  5. JSON-LD Product schema  — Be Bodywise ("category" field in Product JSON-LD)
  6. RSC __next_f data       — Nathabit (collections[].attributes.category.data.attributes.url)
  7. HTML microdata          — Bioderma (schema.org BreadcrumbList in HTML)

Requires:  httpx, beautifulsoup4, psycopg, python-dotenv
Playwright NOT required (be_bodywise serves full HTML without JS rendering).

Usage:
    .venv/bin/python scripts/scrape_breadcrumbs.py
    .venv/bin/python scripts/scrape_breadcrumbs.py --dry-run
    .venv/bin/python scripts/scrape_breadcrumbs.py --brand forest_essentials
    .venv/bin/python scripts/scrape_breadcrumbs.py --limit 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg
import psycopg.rows
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Constants ────────────────────────────────────────────────────────────────

TARGET_SLUGS = [
    "forest_essentials",
    "kama_ayurveda",
    "cetaphil_in",
    "neutrogena_in",
    "mamaearth",
    "nathabit",
    "be_bodywise",
    "plix",
    "thebodyshop_in",
    "olay_in",
    "cerave_in",
    "bioderma_in",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CONCURRENCY = 3
PRODUCTS_PER_BRAND = 100  # test run limit
REQUEST_TIMEOUT = 20.0


# ── DB helpers ───────────────────────────────────────────────────────────────

def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


async def fetch_products(brand_slugs: list[str], limit_per_brand: int) -> list[dict]:
    """Return up to `limit_per_brand` products per brand with NULL category_raw."""
    rows: list[dict] = []
    dsn = _dsn()
    async with await psycopg.AsyncConnection.connect(
        dsn, row_factory=psycopg.rows.dict_row
    ) as conn:
        for slug in brand_slugs:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT DISTINCT ON (p.id)
                        p.id            AS product_id,
                        p.canonical_name,
                        rl.listing_url,
                        r.slug          AS brand_slug
                    FROM core.products p
                    JOIN core.retailer_listings rl ON rl.product_id = p.id
                    JOIN core.retailers r ON r.id = rl.retailer_id
                    WHERE p.category_raw IS NULL
                      AND r.slug = %s
                    ORDER BY p.id
                    LIMIT %s
                    """,
                    (slug, limit_per_brand),
                )
                brand_rows = await cur.fetchall()
                rows.extend(brand_rows)
    return rows


async def update_category_raw(
    conn: psycopg.AsyncConnection,
    product_id: int,
    category_raw: str,
) -> bool:
    """Return True if the row was updated (was still NULL)."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE core.products
            SET    category_raw = %s
            WHERE  id = %s AND category_raw IS NULL
            """,
            (category_raw, product_id),
        )
        return cur.rowcount > 0


# ── Extraction helpers ───────────────────────────────────────────────────────

def _extract_jsonld_breadcrumb(html: str) -> str | None:
    """
    Parse JSON-LD <script type="application/ld+json"> blocks.
    Returns the 2nd-to-last item name (the category, not the product itself).
    e.g. Home > Baby Care > Sunscreen → returns 'Baby Care'
         Home > Product → returns None (only 2 items, no meaningful category level)
    """
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.+?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        raw = match.group(1).strip()
        # Sometimes there are multiple objects — handle both single dict and list
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, list):
            objects = data
        else:
            objects = [data]
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") != "BreadcrumbList":
                continue
            items = obj.get("itemListElement", [])
            if len(items) < 3:
                # Only Home > Product — no category segment
                return None
            # Sort by position to be safe
            try:
                items = sorted(items, key=lambda x: int(x.get("position", 99)))
            except (TypeError, ValueError):
                pass
            # 2nd-to-last = category
            category_item = items[-2]
            name = category_item.get("name") or category_item.get("item", {}).get("name")
            if name:
                return name.strip()
    return None


def _extract_html_microdata_breadcrumb(html: str) -> str | None:
    """
    Parse schema.org BreadcrumbList microdata embedded in HTML.
    Used for Bioderma which renders it server-side.
    Returns the 2nd-to-last item.
    """
    soup = BeautifulSoup(html, "html.parser")
    breadcrumb_list = soup.find(
        attrs={"itemtype": lambda v: v and "BreadcrumbList" in v}
    )
    if not breadcrumb_list:
        return None
    items = breadcrumb_list.find_all(
        attrs={"itemtype": lambda v: v and "ListItem" in v}
    )
    if len(items) < 3:
        return None
    # 2nd-to-last
    target = items[-2]
    name_el = target.find(attrs={"itemprop": "name"})
    if name_el:
        return name_el.get_text(strip=True)
    return None


def _slug_to_label(slug: str) -> str:
    """Convert a URL slug like 'toners-serums-and-masks' → 'Toners Serums and Masks'."""
    return slug.replace("-", " ").title()


def _extract_url_path_category(url: str, slug: str) -> str | None:
    """
    Extract category from URL path for brands where the path encodes it.

    neutrogena_in  : /face/{category}/{product}  → position index 1 (0-based after domain)
    cetaphil_in    : /product-range/{category}/{product-slug}/{id}.html → index 1
    forest_essentials: /catalog/category/view/id/{n}/cat/{cat}.html  [not used]
                      Simple product URLs: /{product}.html — no category segment
    kama_ayurveda  : /{product}.html — no category segment
    """
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]

    if slug == "neutrogena_in":
        # /face/{category}/{product}
        if len(segments) >= 2:
            return _slug_to_label(segments[1])

    elif slug == "cetaphil_in":
        # Multiple URL patterns. The category segment exists only when depth >= 4:
        #   /product-range/{category}/{product-slug}/{id}.html  (depth=4, category=segs[1])
        #   /products/{category}/{product-slug}/{id}.html       (depth=4, category=segs[1])
        #   /product-categories/{category}/{product-slug}/{id}  (depth=4, category=segs[1])
        #   /products-1/{product-slug}/{id}.html                (depth=3, NO category segment)
        _CETAPHIL_ROOTS = {"product-range", "products", "product-categories"}
        if len(segments) >= 4 and segments[0] in _CETAPHIL_ROOTS:
            # Skip if the second segment looks like an ID/SKU (starts with digit)
            label = _slug_to_label(segments[1])
            # Exclude meta-navigation labels that aren't real product categories
            if not segments[1][:1].isdigit() and label.lower() not in (
                "product categories", "product range", "products",
            ):
                return label

    return None


def _extract_bebodywise_category(html: str) -> str | None:
    """
    Be Bodywise: JSON-LD Product schema has a "category" field.
    e.g. "category":"hair"
    """
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.+?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, list):
            objects = data
        else:
            objects = [data]
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            # Look for @type=Product with a category field
            obj_type = obj.get("@type", "")
            if "Product" in obj_type or obj_type == "ItemList":
                cat = obj.get("category")
                if cat and isinstance(cat, str) and cat.lower() not in ("", "undefined"):
                    return cat.strip().title()
    return None


def _extract_plix_category(html: str) -> str | None:
    """
    Plix: NEXT_DATA contains metadata key 'search_product_type'.
    e.g. {"key": "search_product_type", "value": "Serum"}
    """
    m = re.search(
        r'<script id=["\']__NEXT_DATA__["\'][^>]*>(.+?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None

    ppd = (
        data.get("props", {})
        .get("pageProps", {})
        .get("productPageData", {})
    )
    product = ppd.get("product", {}) if isinstance(ppd, dict) else {}
    for meta in product.get("metadata", []):
        if isinstance(meta, dict) and meta.get("key") == "search_product_type":
            val = meta.get("value", "").strip()
            if val:
                return val
    return None


def _extract_thebodyshop_category(html: str) -> str | None:
    """
    The Body Shop India: NEXT_DATA → initialState →
    productDetailReducer.product.categoryData.child_category.name
    Falls back to categoryData.name if child_category is absent.
    """
    m = re.search(
        r'<script id=["\']__NEXT_DATA__["\'][^>]*>(.+?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None

    detail = (
        data.get("props", {})
        .get("pageProps", {})
        .get("initialState", {})
        .get("productDetailReducer", {})
        .get("product", {})
    )
    if not isinstance(detail, dict):
        return None
    cat_data = detail.get("categoryData", {})
    if not isinstance(cat_data, dict):
        return None
    child = cat_data.get("child_category", {})
    if child and isinstance(child, dict) and child.get("name"):
        return child["name"].strip()
    if cat_data.get("name"):
        return cat_data["name"].strip()
    return None


def _extract_forest_essentials_category(html: str) -> str | None:
    """
    Forest Essentials: Magento 2 site where the breadcrumb is JS-rendered.
    The dataLayer GA ecommerce push contains a 'category' field — comma-separated
    list like "Facial Care,Luxurious Ayurveda,Ubtans,..."
    We take the first (most specific top-level) entry.
    """
    # Match dataLayer.push({...}) calls
    for m in re.finditer(r'dataLayer\.push\s*\((.+?)\)', html, re.DOTALL):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        ecom = data.get("ecommerce", {})
        if not isinstance(ecom, dict):
            continue
        products = ecom.get("detail", {}).get("products", {})
        if not isinstance(products, dict):
            continue
        cat_str = products.get("category", "")
        if cat_str and isinstance(cat_str, str):
            # First entry is the top-level category
            first = cat_str.split(",")[0].strip()
            if first:
                return first
    return None


def _extract_kama_ayurveda_category(html: str) -> str | None:
    """
    Kama Ayurveda: Next.js + Apollo GraphQL CMS.
    NEXT_DATA → props.pageProps contains:
      - initialApolloState: has CategoryTree:<id> entries with name
      - pdp.data.products.items[0].categories: list of category dicts

    We prefer the most specific non-generic CategoryTree name.
    Fallback: pdp.data.products.items[0].primary_category.
    """
    m = re.search(
        r'<script id=["\']__NEXT_DATA__["\'][^>]*>(.+?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None

    pp = data.get("props", {}).get("pageProps", {})

    # Strategy A: Apollo state CategoryTree entries (most precise)
    apollo = pp.get("initialApolloState", {})
    tree_names = sorted(set(
        v.get("name", "").strip()
        for k, v in apollo.items()
        if k.startswith("CategoryTree:") and isinstance(v, dict) and v.get("name")
    ))
    # Filter out noise: short generic names and navigation-only categories
    _NOISE_KAMA = {
        "shop", "by category", "by concern", "minis", "sale", "new",
        "bestsellers", "gifting", "certifiedorganic", "collection",
        "men's", "kama essentials", "the best of kama", "best of kama ayurveda",
        "top products of kama ayurveda", "advantage club exclusive offers",
        "limited period offer | kama ayurveda", "buy 1 get 3", "summer soirée",
        "flash sale", "winter rituals", "happy hours", "shop the best",
        "best sellers", "by concern", "happy hydration", "oil station",
        "haircare & bodycare bestsellers", "winter",
    }
    useful = [
        n for n in tree_names
        if n.lower().strip() not in _NOISE_KAMA
        and len(n) > 3
        and not any(kw in n.lower() for kw in [
            "flash", "sale", "offer", "exclusive", "hour", "season",
            "limited", "club", "soirée", "ritual", "combo", "buy 1",
            "happy hour", "winter ritual"
        ])
    ]
    if len(useful) == 1:
        return useful[0]
    # If multiple, prefer those that aren't just a line/set/kit indicator
    specific = [n for n in useful if not any(
        kw in n.lower() for kw in ["set", "kit", "combo", "discovery", "collection", "amarrupa"]
    )]
    if specific:
        return specific[0]
    if useful:
        return useful[0]

    # Strategy B: pdp.data.products.items[0].categories — pick least generic
    items = pp.get("pdp", {}).get("data", {}).get("products", {}).get("items", [])
    if items:
        cats = items[0].get("categories", [])
        cat_names = [c.get("name", "").strip() for c in cats if isinstance(c, dict)]
        # Filter to meaningful product categories
        meaningful = [
            n for n in cat_names
            if n and n.lower().strip() not in _NOISE_KAMA and len(n) > 3
            and not any(kw in n.lower() for kw in [
                "flash", "sale", "offer", "exclusive", "hour", "buy 1",
                "limited", "club", "season", "soirée",
            ])
        ]
        if meaningful:
            return meaningful[0]

    # Strategy C: primary_category (generic — "Skin Care", "Body Care", "Hair Care")
    if items:
        primary = items[0].get("primary_category", "")
        if primary and isinstance(primary, str) and primary.strip():
            return primary.strip()

    return None


def _extract_nathabit_category(html: str) -> str | None:
    """
    Nathabit: Next.js App Router (RSC). The page embeds product data via
    __next_f.push([1, "..."]) chunks. The chunk containing the product's
    collections has:
      "collections":{"data":[{"attributes":{"url":"<collection>",
        "category":{"data":{"attributes":{"url":"<category-url>"}}}}}]}

    We extract the first collection's category URL and convert to a label.
    e.g. "body-care" → "Body Care"
    """
    # Strategy 1: look for the compact RSC serialization format in push chunks
    # Pattern: "categoryUrl":"<url>" appears in related-product blocks for the
    # same product category
    pushes = re.findall(
        r'self\.__next_f\.push\(\[1,"(.+?)"\]\)',
        html,
        re.DOTALL,
    )
    for raw_push in pushes:
        try:
            chunk = json.loads(f'"{raw_push}"')
        except (json.JSONDecodeError, ValueError):
            chunk = raw_push

        # Strategy 1a: full JSON format from __next_f push chunk 86+
        # "collections":{"data":[{"attributes":{"url":"...", "category":{"data":{"attributes":{"url":"body-care"}}}}}]}
        m = re.search(
            r'"collections"\s*:\s*\{"data"\s*:\s*\[\{"attributes"\s*:\s*\{'
            r'[^}]*"category"\s*:\s*\{"data"\s*:\s*\{"attributes"\s*:\s*\{"url"\s*:\s*"([^"]+)"',
            chunk,
        )
        if m:
            return _slug_to_label(m.group(1))

    # Strategy 2: search for categoryUrl in the rendered RSC output
    # "categoryUrl":"body-care" appears in product swiper blocks for THIS product
    # Find the specific product's categoryUrl by looking near its URL
    all_rsc = " ".join(pushes)
    try:
        all_rsc_decoded = json.loads(f'"{all_rsc}"')
    except (json.JSONDecodeError, ValueError):
        all_rsc_decoded = all_rsc

    cat_urls = re.findall(r'"categoryUrl"\s*:\s*"([^"]+)"', all_rsc_decoded)
    if cat_urls:
        # Return the most-frequent one (the product's own category)
        from collections import Counter
        most_common = Counter(cat_urls).most_common(1)[0][0]
        return _slug_to_label(most_common)

    return None


# ── Per-brand dispatcher ─────────────────────────────────────────────────────

def extract_category(html: str, url: str, brand_slug: str) -> str | None:
    """
    Try all extraction strategies in priority order for the given brand.
    Returns the raw category string (as the brand labels it) or None.
    """

    # 1. JSON-LD BreadcrumbList ≥3 items (Mamaearth, CeraVe, Olay — others only have 2)
    cat = _extract_jsonld_breadcrumb(html)
    if cat:
        return cat

    # 2. Brand-specific URL-path extraction
    cat = _extract_url_path_category(url, brand_slug)
    if cat:
        return cat

    # 3. The Body Shop India — NEXT_DATA
    if brand_slug == "thebodyshop_in":
        cat = _extract_thebodyshop_category(html)
        if cat:
            return cat

    # 4. Plix — NEXT_DATA metadata search_product_type
    if brand_slug == "plix":
        cat = _extract_plix_category(html)
        if cat:
            return cat

    # 5. Kama Ayurveda — NEXT_DATA Apollo GraphQL
    if brand_slug == "kama_ayurveda":
        cat = _extract_kama_ayurveda_category(html)
        if cat:
            return cat

    # 6. Forest Essentials — dataLayer GA ecommerce push
    if brand_slug == "forest_essentials":
        cat = _extract_forest_essentials_category(html)
        if cat:
            return cat

    # 7. Be Bodywise — JSON-LD Product schema category field
    if brand_slug == "be_bodywise":
        cat = _extract_bebodywise_category(html)
        if cat:
            return cat

    # 8. Nathabit — RSC __next_f data
    if brand_slug == "nathabit":
        cat = _extract_nathabit_category(html)
        if cat:
            return cat

    # 9. HTML microdata (Bioderma)
    cat = _extract_html_microdata_breadcrumb(html)
    if cat:
        return cat

    return None


# ── Async scraping worker ────────────────────────────────────────────────────

async def scrape_one(
    client: httpx.AsyncClient,
    product: dict,
    sem: asyncio.Semaphore,
) -> dict:
    """Fetch a product page and extract its category. Returns enriched dict."""
    result = {
        "product_id": product["product_id"],
        "canonical_name": product["canonical_name"],
        "brand_slug": product["brand_slug"],
        "url": product["listing_url"],
        "category": None,
        "error": None,
    }
    async with sem:
        try:
            resp = await client.get(product["listing_url"], timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
            result["category"] = extract_category(html, product["listing_url"], product["brand_slug"])
        except httpx.HTTPStatusError as exc:
            result["error"] = f"HTTP {exc.response.status_code}"
        except httpx.RequestError as exc:
            result["error"] = f"RequestError: {exc}"
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"Unexpected: {exc}"
    return result


# ── Main ─────────────────────────────────────────────────────────────────────

async def run(brand_filter: str | None, dry_run: bool, limit: int) -> None:
    slugs = [brand_filter] if brand_filter else TARGET_SLUGS
    # Validate
    for s in slugs:
        if s not in TARGET_SLUGS:
            raise ValueError(f"Unknown brand slug: {s!r}. Valid: {TARGET_SLUGS}")

    print(f"\n{'='*60}")
    print(f"  Breadcrumb scraper — {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"  Brands: {slugs}")
    print(f"  Limit per brand: {limit}")
    print(f"{'='*60}\n")

    products = await fetch_products(slugs, limit)
    print(f"Fetched {len(products)} products with NULL category_raw\n")
    if not products:
        print("Nothing to do.")
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    transport = httpx.AsyncHTTPTransport(retries=1)
    async with httpx.AsyncClient(
        headers=HEADERS, follow_redirects=True, transport=transport
    ) as client:
        tasks = [scrape_one(client, p, sem) for p in products]
        results: list[dict] = []
        start = time.perf_counter()
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            res = await coro
            results.append(res)
            status = res["category"] or res["error"] or "—"
            print(
                f"  [{i:4d}/{len(tasks)}] "
                f"{res['brand_slug']:20s} "
                f"{res['canonical_name'][:45]:45s} → {status}"
            )
        elapsed = time.perf_counter() - start

    # ── Write to DB ──────────────────────────────────────────────────────────
    brand_stats: dict[str, dict] = {}
    for s in slugs:
        brand_stats[s] = {"found": 0, "not_found": 0, "errors": 0, "samples": []}

    updated_total = 0
    if not dry_run:
        async with await psycopg.AsyncConnection.connect(
            _dsn(), row_factory=psycopg.rows.dict_row
        ) as conn:
            for res in results:
                bs = res["brand_slug"]
                if res["error"]:
                    brand_stats[bs]["errors"] += 1
                elif res["category"]:
                    brand_stats[bs]["found"] += 1
                    if len(brand_stats[bs]["samples"]) < 5:
                        brand_stats[bs]["samples"].append(res["category"])
                    was_updated = await update_category_raw(
                        conn, res["product_id"], res["category"]
                    )
                    if was_updated:
                        updated_total += 1
                else:
                    brand_stats[bs]["not_found"] += 1
            await conn.commit()
    else:
        for res in results:
            bs = res["brand_slug"]
            if res["error"]:
                brand_stats[bs]["errors"] += 1
            elif res["category"]:
                brand_stats[bs]["found"] += 1
                if len(brand_stats[bs]["samples"]) < 5:
                    brand_stats[bs]["samples"].append(res["category"])
            else:
                brand_stats[bs]["not_found"] += 1

    # ── Report ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  RESULTS SUMMARY")
    print(f"{'='*60}")
    total_found = sum(v["found"] for v in brand_stats.values())
    total_not_found = sum(v["not_found"] for v in brand_stats.values())
    total_errors = sum(v["errors"] for v in brand_stats.values())

    print(f"\n{'Brand':25s} {'Found':>6s} {'NoCategory':>11s} {'Errors':>7s}  Sample values")
    print("-" * 90)
    for s, stats in brand_stats.items():
        samples_str = ", ".join(set(stats["samples"][:5])) if stats["samples"] else "—"
        print(
            f"  {s:23s} {stats['found']:6d} {stats['not_found']:11d} "
            f"{stats['errors']:7d}  {samples_str}"
        )
    print("-" * 90)
    print(f"  {'TOTAL':23s} {total_found:6d} {total_not_found:11d} {total_errors:7d}")

    print(f"\n  Total scraped: {len(results)}")
    print(f"  Category found: {total_found}")
    print(f"  No category: {total_not_found}")
    print(f"  Errors: {total_errors}")
    if not dry_run:
        print(f"  DB rows updated: {updated_total}")
    else:
        print("  [DRY RUN] — no DB writes.")

    print(f"\n  Elapsed: {elapsed:.1f}s  ({elapsed/len(results):.2f}s per product)")

    # Estimate full run
    all_nulls = {
        "forest_essentials": 43, "kama_ayurveda": 124, "cetaphil_in": 28,
        "neutrogena_in": 39, "mamaearth": 498, "nathabit": 302, "be_bodywise": 24,
        "plix": 246, "thebodyshop_in": 218, "olay_in": 24, "cerave_in": 13,
        "bioderma_in": 48,
    }
    total_remaining = sum(all_nulls.get(s, 0) for s in slugs)
    per_product_s = elapsed / len(results) if results else 1.0
    estimated_full_s = total_remaining * per_product_s
    print(f"\n  Full-run estimate: {total_remaining} products × {per_product_s:.2f}s "
          f"= ~{estimated_full_s:.0f}s ({estimated_full_s/60:.1f} min)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape breadcrumb categories for non-Shopify brands."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing to DB.")
    parser.add_argument("--brand", metavar="SLUG",
                        help="Scrape only this brand slug.")
    parser.add_argument("--limit", type=int, default=PRODUCTS_PER_BRAND,
                        help=f"Products per brand (default: {PRODUCTS_PER_BRAND}).")
    args = parser.parse_args()
    asyncio.run(run(brand_filter=args.brand, dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
