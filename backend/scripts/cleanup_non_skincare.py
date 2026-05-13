"""
Delete non-skincare products from core.products.

Wand is a skincare platform — valid products are face skincare, body skincare,
lip care, and eye care. This script removes:

  1. Pharmaceuticals / medicines    — Himalaya tablets, syrups, drops, ointments
  2. Baby care                       — diapers, baby wash, baby soap, baby rash cream
  3. Pet products / food             — Himalaya pet food, pet cleanser
  4. Food & beverages                — Himalaya green tea, supplements
  5. Household / non-cosmetic        — toothpaste, mouthwash, laundry wash
  6. Pure haircare                   — shampoo, conditioner (not scalp treatments)
  7. Pure makeup (non-skincare)      — eyeshadow, liner, mascara, foundation, etc.
  8. Merchandise / gift cards / books

  BORDERLINE KEPT (not deleted):
  - Makeup removers / cleansing oils  — these are skincare-function products
  - Lip masks / lip patches           — skincare
  - Pixi "Lips" category              — lip treatments, not lipsticks

Usage:
    python -m scripts.cleanup_non_skincare            # dry-run (default)
    python -m scripts.cleanup_non_skincare --execute  # actually delete
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
log = structlog.get_logger()

# ── Deletion rules ────────────────────────────────────────────────────────────

# category_raw exact values that are definitively non-skincare
NON_SKINCARE_CATEGORY_RAW: list[str] = [
    # Pharmaceuticals / dosage forms
    "Syrup", "Liquid", "Drops", "Caplet", "Bolus", "Granules", "Resin",
    "Lozenge", "MDT (Tablet)", "Ointment",
    # Baby care
    "Baby Care", "Baby Care Products", "Baby Skin Care Products",
    "Baby Body Wash", "Baby Diaper", "Baby Rash Cream", "Baby Face Wash",
    "Baby Soap", "Baby Rub", "Baby Bar",
    # Pet / household / food
    "Pet Cleanser", "Food", "Beverage", "Laundry Wash", "Toothpaste", "Mouthwash",
    "Diaper",
    # Pure makeup (not skincare-function)
    "MakeupSingle", "Makeup combos", "Makeup Products", "Clean Makeup",
    "Makeup", "shadow", "liner", "bronzer", "brow", "brow pencil",
    "highlighter", "primer", "powder", "Self Tanner",
    "Makeup Bundle", "Makeup Base & Primer",
    "Makeup Setting Spray", "Makeup Combo", "Skin and Makeup Combo",
    "Makeup Puff",
    "High Impact, Active Botanical Packed Skincare and Makeup",
    "High Impact, Active Botanical Packed Skincare and Haircare",
    "Clean Makeup with Real Skincare Ingredients",
    # Pure haircare
    "Hair Care", "Best Hair Care Products",
    # Merchandise / gift cards / books
    "Merch", "Merchandise", "Gift Card", "Gift Cards", "Books", "Book",
]

# category_raw ILIKE patterns
NON_SKINCARE_CATEGORY_RAW_ILIKE: list[str] = [
    "%baby diaper%",
    "%baby toothpaste%",
    "%baby bath%",
    "%baby soap%",
    "%baby cream%",
    "%beard oil%",
    "%hair spray%",
    "%hair styling%",
    "%hair accessories%",
    "%hair color%",
    "%hair colour%",
]

# canonical_name ILIKE patterns — catches products that slipped past category filters
NON_SKINCARE_NAME_ILIKE: list[str] = [
    "% tablet%",
    "% tablets%",
    "%capsules%",       # plural only — avoids "Capsule Cream" / "CapsuleCare" false positives
    "% syrup%",
    "%pet food%",
    "%pet cleanser%",
    "% diaper%",
    "%toothpaste%",
    "%mouthwash%",
    "%shampoo%",
    "%conditioner%",      # haircare — but NOT "skin conditioner"
    "% dog %",
    "% cat food%",
    "%laundry%",
    "%bolus%",
    "%granules%",
    "%lozenge%",
    "%ointment%",
    "%bolus%",
]

# canonical_name patterns that should be KEPT even if they match above
# (used to carve out exceptions for ambiguous terms)
KEEP_NAME_ILIKE: list[str] = [
    "%skin conditioner%",   # e.g. "Gentle Skin Conditioner"
    "%hair conditioner mask%",  # could be borderline
]


def _build_delete_where() -> tuple[str, list]:
    parts: list[str] = []
    params: list = []

    # Exact category_raw matches
    if NON_SKINCARE_CATEGORY_RAW:
        placeholders = ",".join(["%s"] * len(NON_SKINCARE_CATEGORY_RAW))
        parts.append(f"p.category_raw IN ({placeholders})")
        params.extend(NON_SKINCARE_CATEGORY_RAW)

    # ILIKE category_raw patterns
    for pat in NON_SKINCARE_CATEGORY_RAW_ILIKE:
        parts.append("p.category_raw ILIKE %s")
        params.append(pat)

    # ILIKE name patterns
    for pat in NON_SKINCARE_NAME_ILIKE:
        parts.append("p.canonical_name ILIKE %s")
        params.append(pat)

    where = "(" + " OR ".join(parts) + ")"

    # Carve out exceptions
    keep_parts = []
    keep_params: list = []
    for pat in KEEP_NAME_ILIKE:
        keep_parts.append("p.canonical_name ILIKE %s")
        keep_params.append(pat)
    if keep_parts:
        where += " AND NOT (" + " OR ".join(keep_parts) + ")"
        params.extend(keep_params)

    return where, params


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true",
                        help="Actually delete (default is dry-run)")
    args = parser.parse_args()

    db_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    conn = await psycopg.AsyncConnection.connect(db_url, row_factory=dict_row)

    where, params = _build_delete_where()

    # ── Dry-run: show breakdown by brand + reason ──────────────────────────
    print("\n=== Non-skincare products to delete ===\n")

    cur = await conn.execute(f"""
        SELECT b.name, p.category_raw, count(*) as cnt
        FROM core.products p
        JOIN core.brands b ON b.id = p.brand_id
        WHERE {where}
        GROUP BY b.name, p.category_raw
        ORDER BY b.name, cnt DESC
    """, params)
    rows = await cur.fetchall()

    brand_totals: dict[str, int] = {}
    for r in rows:
        brand_totals[r["name"]] = brand_totals.get(r["name"], 0) + r["cnt"]

    current_brand = None
    grand_total = 0
    for r in rows:
        if r["name"] != current_brand:
            if current_brand:
                print(f"    → subtotal: {brand_totals[current_brand]}")
                print()
            current_brand = r["name"]
            print(f"  {r['name']}:")
        print(f"    {str(r['category_raw']):<45}  {r['cnt']:>4}x")
        grand_total += r["cnt"]
    if current_brand:
        print(f"    → subtotal: {brand_totals[current_brand]}")

    print(f"\n  TOTAL to delete: {grand_total}")

    # Also show total remaining after delete
    cur = await conn.execute("SELECT count(*) FROM core.products")
    total_before = (await cur.fetchone())["count"]
    print(f"  Products before: {total_before}")
    print(f"  Products after:  {total_before - grand_total}")

    if not args.execute:
        print("\n  ⚠️  DRY RUN — pass --execute to actually delete\n")
        await conn.close()
        return

    # ── Execute ────────────────────────────────────────────────────────────
    # Collect IDs first, then delete dependents before products
    cur = await conn.execute(f"""
        SELECT p.id FROM core.products p WHERE {where}
    """, params)
    rows = await cur.fetchall()
    product_ids = [r["id"] for r in rows]

    if not product_ids:
        print("\n  Nothing to delete.\n")
        await conn.close()
        return

    ids = product_ids
    id_ph = ",".join(["%s"] * len(ids))

    # Get listing IDs for these products first
    cur = await conn.execute(
        f"SELECT id FROM core.retailer_listings WHERE product_id IN ({id_ph})", ids
    )
    listing_ids = [r["id"] for r in await cur.fetchall()]
    l_ph = ",".join(["%s"] * len(listing_ids)) if listing_ids else None

    # Delete in FK dependency order (deepest dependents first)
    if l_ph:
        await conn.execute(f"DELETE FROM scraping.ingredient_extraction_queue WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM scraping.human_review_queue WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM scraping.repair_queue WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM core.price_history WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM core.price_history_2026_04 WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM core.price_history_2026_05 WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM core.promotions WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM core.raw_scrapes WHERE listing_id IN ({l_ph})", listing_ids)
        await conn.execute(f"DELETE FROM core.retailer_listings WHERE product_id IN ({id_ph})", ids)

    await conn.execute(f"DELETE FROM scraping.ingredient_extraction_queue WHERE product_id IN ({id_ph})", ids)
    await conn.execute(f"DELETE FROM core.product_ingredients WHERE product_id IN ({id_ph})", ids)
    await conn.execute(f"DELETE FROM users.shelf_items WHERE product_id IN ({id_ph})", ids)

    cur = await conn.execute(f"DELETE FROM core.products WHERE id IN ({id_ph})", ids)
    deleted = cur.rowcount
    await conn.commit()
    print(f"\n  ✅ Deleted {deleted} products (+ all dependent records).\n")
    log.info("cleanup_complete", deleted=deleted)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
