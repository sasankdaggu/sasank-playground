"""
Bulk keyword-based assignment of canonical_category_id to core.products.

Rules:
  - Checks product name (canonical_name) and category_raw for keywords.
  - Only assigns when canonical_category_id IS NULL (never overwrites a
    manually-set or previously-assigned category).
  - Applies EXCLUSION guards first (body/sunscreen) before positive matches.
  - Runs over ALL products across all brands.

Usage:
    .venv/bin/python scripts/assign_canonical_categories.py
    .venv/bin/python scripts/assign_canonical_categories.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

log = structlog.get_logger()

# ── Exclusion guards (applied first, before any positive match) ──────────────
# If any of these appear in lowercased canonical_name, skip assigning face-* category.
BODY_TOKENS = frozenset({
    "body lotion", "body moisturizer", "body moisturiser", "body cream",
    "body butter", "body milk", "body wash", "body scrub", "body oil",
    "body mist", "body serum",
    "hand cream", "hand lotion", "hand wash",
    "foot cream", "foot lotion", "foot scrub",
    "shower cream", "shower gel", "bath ",
    "baby cream", "baby lotion", "massage cream", "massage lotion",
    "stretch marks cream",  # body treatment
    "underarm",
})

# Products with SPF/sunscreen in name → goes into sunscreens (id=22), not moisturizers
SPF_TOKENS = frozenset({
    " spf ", "spf+", "spf-", "spf50", "spf30", "spf20",
    "sunscreen", "suncream", "sun cream",
    "pa+", "pa++", "pa+++", "pa++++",
    "uva/b",
})

# Hair-specific tokens — exclude from face/body rules
HAIR_TOKENS = frozenset({
    "hair oil", "hair serum", "hair mask", "hair cream", "hair lotion",
    "hair balm", "hair butter", "hair mist", "hair spray", "hair drops",
    "shampoo", "conditioner",
    "scalp", "hair growth", "hair fall", "anti-hairfall", "anti hairfall",
    "beard", "argan oil shots",  # hair treatment oil shots
})


def _is_hair_product(name_lower: str) -> bool:
    return any(t in name_lower for t in HAIR_TOKENS)


# Lip-specific tokens (so booster/essence etc. don't bleed into face-serums)
LIP_TOKENS = frozenset({"lip ", " lip", "lip balm", "lip mask", "lip scrub", "lip butter"})


def _is_lip_product(name_lower: str) -> bool:
    return any(t in name_lower for t in LIP_TOKENS)


# Eye-specific tokens
EYE_TOKENS = frozenset({"eye cream", "eye serum", "eye patch", "under eye", "under-eye", "dark circle"})


def _is_eye_product(name_lower: str) -> bool:
    return any(t in name_lower for t in EYE_TOKENS)


def _is_body_product(name_lower: str) -> bool:
    return any(t in name_lower for t in BODY_TOKENS)


def _is_sunscreen(name_lower: str) -> bool:
    return any(t in name_lower for t in SPF_TOKENS)


def _should_exclude_from_face_moisturizer(name_lower: str) -> bool:
    """Return True if this product should NOT be assigned to face-moisturizers."""
    return _is_body_product(name_lower) or _is_sunscreen(name_lower)


def _should_exclude_from_face_serums(name_lower: str) -> bool:
    """Prevent hair/lip/body products from falling into face-serums."""
    return _is_body_product(name_lower) or _is_hair_product(name_lower) or _is_lip_product(name_lower)


def _should_exclude_from_face_cleansers(name_lower: str) -> bool:
    """Prevent body wash/hair shampoo from falling into face-cleansers."""
    return (
        _is_body_product(name_lower)
        or _is_hair_product(name_lower)
        or "body" in name_lower
        or "shampoo" in name_lower
    )


# ── Category-specific keyword sets ──────────────────────────────────────────
# Each entry: (category_slug, id, name_keywords, category_raw_keywords)
# name_keywords: list of lowercase strings that, when found in canonical_name,
#   indicate this category.
# category_raw_keywords: list of strings matched case-insensitively against
#   category_raw; supplements name matching.
#
# IMPORTANT: for face-moisturizers, "cream" alone is intentionally NOT listed
# as a standalone name keyword (too broad — "sunscreen", "eye cream", "body cream"
# all contain "cream"). Instead we use compound/specific terms.
# category_raw="Face Cream" IS used because retailer already classified it.

CATEGORY_RULES: list[dict] = [
    # ── id=8  face-moisturizers ──────────────────────────────────────────────
    # Original keywords (pre-fix): only "moisturizer", "moisturiser" in name,
    # plus category_raw in Moisturizer/Moisturiser/Face Cream/Face Moisturizer/etc.
    # Missing: strobe cream, night gel, jello, milk fluid, gel cream, hydra gel,
    #          night cream, day cream, barrier cream, dream cream
    {
        "slug": "face-moisturizers",
        "id": 8,
        "name_keywords": [
            "moisturizer",
            "moisturiser",
            # Compound cream terms — specific enough to avoid false positives
            "strobe cream",
            "night cream",
            "day cream",
            "dream cream",
            "barrier cream",
            "gel cream",
            "hydra gel",          # Aqualogica-specific: "Hydra Gel Moisturizer"
            "night gel",          # Plum-specific: "Night Gel" is a face moisturizer format
            "jello moisturizer",  # Aqualogica JellO Moisturizer
            "jell-o moisturizer",
            "jell-o moisturiser",
            "milk fluid moisturizer",  # Aqualogica Milk Fluid Moisturizer
            "milk fluid moisturiser",
            "fluid moisturizer",
            "fluid moisturiser",
            "repair moisturizer",
            "repair moisturiser",
        ],
        "category_raw_keywords": [
            "moisturizer",
            "moisturiser",
            "moisturisers",
            "moisturizers",
            "face cream",
            "face creams",
            "face creams & moisturizers",
            "face moisturizer",
            "face moisturiser",
            "illuminating moisturizer",
            "night cream",
            "day cream",
            "night care",        # retailers sometimes use this for night creams
            "hydrate",           # 82°E raw category: "Hydrate" = face moisturizer/gel
        ],
        "exclude_fn": _should_exclude_from_face_moisturizer,
    },
    # ── id=9  face-serums ─────────────────────────────────────────────────────
    {
        "slug": "face-serums",
        "id": 9,
        "name_keywords": [
            "face serum",
            "concentrate serum",
            "essence serum",
            "hydrating serum",
            "brightening serum",
            "vitamin c serum",
            "niacinamide serum",
            "retinol serum",
            "peptide serum",
            "skin serum",
            # Standalone 'serum' in name (padded with spaces to avoid partial matches)
            " serum ",
            " serum,",
            # Ampoule / concentrate / booster formats
            "ampoule",
            "face concentrate",
            "skin concentrate",
            "glow booster",          # e.g. "Radiance Glow Booster"
            "de-pigmentation booster",
            "hydration booster",
            "peptide booster",
            "retinal booster",
            "booster complex",       # e.g. "6 Peptide Booster Complex"
            "azelaic acid booster",
            "niacinamide booster",
            "vitamin c booster",
            "c15 super booster",
            "pro-collagen multi-peptide booster",
            # Essence formats (Korean / Ayurvedic)
            "milky essence",
            "treatment essence",
            "activating essence",
            "invigorating essence",
            "face essence",
            "skin essence",
            "vegan mucin face essence",
            "cica & hya",            # Cica & Hya-Betaine face essence
        ],
        "category_raw_keywords": [
            "serum",
            "face serum",
            "serums",
            "essence",
            "ampoule",
            "concentrate",
            "booster",
            "treatment",             # Paula's Choice "Treatment" raw category
        ],
        "exclude_fn": _should_exclude_from_face_serums,
    },
    # ── id=10  face-cleansers ─────────────────────────────────────────────────
    {
        "slug": "face-cleansers",
        "id": 10,
        "name_keywords": [
            "face wash",
            "facewash",              # no-space variant (Lotus, Plix, etc.)
            "foam cleanser",
            "foaming cleanser",
            "gel cleanser",
            "cleansing balm",
            "cleansing oil",
            "micellar water",
            "micellar cleanser",
            "makeup remover",
            "cleansing milk",
            "smoothie face wash",    # Aqualogica naming
            "mousse hydrating foam", # Aqualogica naming
            # Standalone 'cleanser' in name
            " cleanser",
            "cleanser ",
            # Other face wash variants
            "facial cleanser",
            "gentle cleanser",
            "hydrating cleanser",
            "brightening cleanser",
            "oil cleanser",          # not "cleansing oil" but "oil cleanser"
        ],
        "category_raw_keywords": [
            "face wash",
            "cleanser",
            "cleansers",
            "cleansing",
            "cleanse",               # 82°E raw category
        ],
        "exclude_fn": _should_exclude_from_face_cleansers,
    },
    # ── id=11  face-toners ────────────────────────────────────────────────────
    {
        "slug": "face-toners",
        "id": 11,
        "name_keywords": [
            "toner",
            "toning mist",
            "toning water",
            "facial mist",
            "face mist",
            "essence toner",
            "lotion toner",
            "hydrating mist",
            "facial spray",
            "skin toner",
        ],
        "category_raw_keywords": [
            "toner",
            "toners",
            "toning mist",
            "mist",
            "face mist",
            "facial mist",
        ],
        "exclude_fn": None,
    },
    # ── id=22  sunscreens ─────────────────────────────────────────────────────
    {
        "slug": "sunscreens",
        "id": 22,
        "name_keywords": [
            "sunscreen",
            "suncream",
            "sun cream",
            "spf 50",
            "spf50",
            "spf 30",
            "spf30",
            "spf 20",
            "spf20",
            "spf 40",
            "spf40",
            "dewy sunscreen",  # Aqualogica-specific
            "dewy gel sunscreen",
            "sun stick",
            "sunstick",
            "uv protect",
            "uv protection",
            "uv screen",
            "sun protect",
            "porescreen",      # Paula's Choice Porescreen SPF
        ],
        "category_raw_keywords": [
            "sunscreen",
            "sun care",
            "sun protection",
            "spf",
            "uv",
        ],
        "exclude_fn": None,
    },
    # ── id=12  face-masks ─────────────────────────────────────────────────────
    {
        "slug": "face-masks",
        "id": 12,
        "name_keywords": [
            "face mask",
            "sheet mask",
            "clay mask",
            "sleeping mask",
            "overnight mask",
            "peel-off mask",
            "mud mask",
            # Face pack = Indian term for face mask
            "face pack",
            # Ubtan = traditional Indian face mask/exfoliating treatment
            "facial ubtan",
            "ubtan face",
            "ubtan detan",
            # Other mask formats
            "mud pack",
            "clay pack",
            "charcoal mask",
            "charcoal face",
            "peel off mask",
            "detox mask",
            "brightening mask",
            "hydrating mask",
            "anti-acne mask",
            "anti acne mask",
        ],
        "category_raw_keywords": [
            "face mask",
            "mask",
            "sheet mask",
            "face pack",
        ],
        "exclude_fn": None,
    },
    # ── id=11 face-toners (already above) ────────────────────────────────────
    # ── id=13  face-exfoliators ───────────────────────────────────────────────
    {
        "slug": "face-exfoliators",
        "id": 13,
        "name_keywords": [
            "face scrub",
            "facial scrub",
            "exfoliator",
            "exfoliating",
            "gentle melt exfoliator",  # Aqualogica-specific
            "peeling gel",
            "peeling mask",
            "peeling solution",        # Not a face-peel pad but liquid exfoliant
            "ubtan scrub",
            "aha toner",               # AHA/BHA toners = exfoliating toners
            "bha toner",
            "pha toner",
            "glycolic toner",
            "lactic acid toner",
            "salicylic acid toner",
        ],
        "category_raw_keywords": [
            "scrub",
            "exfoliator",
            "exfoliating",
            "peeling",
        ],
        "exclude_fn": None,
    },
    # ── id=14  face-oils ──────────────────────────────────────────────────────
    {
        "slug": "face-oils",
        "id": 14,
        "name_keywords": [
            "face oil",
            "facial oil",
            "rosehip oil",
            "marula oil",
            "bakuchiol oil",
            "skin oil",
            "face serum oil",
            "bakuchiol slip",         # 82°E "Bakuchiol Slip" (face oil, category_raw=Hydrate handled above)
        ],
        "category_raw_keywords": [
            "face oil",
            "facial oil",
            "face oils",
        ],
        "exclude_fn": None,
    },
    # ── id=24  eye-creams ─────────────────────────────────────────────────────
    {
        "slug": "eye-creams",
        "id": 24,
        "name_keywords": [
            "eye cream",
            "eye serum",
            "under eye",
            "under-eye",
            "dark circle",
            "eye gel",
        ],
        "category_raw_keywords": [
            "eye cream",
            "eye care",
            "under eye",
        ],
        "exclude_fn": None,
    },
    # ── id=27  lip-balms ──────────────────────────────────────────────────────
    # NOTE: lip-scrubs (id=28) and lip-masks (id=29) are evaluated AFTER this
    # because lip-scrub/lip-mask name keywords are specific enough to not hit here,
    # and category_raw "lip" is intentionally NOT included (too broad) to avoid
    # consuming lip scrub / lip mask products that also have category_raw containing "lip".
    {
        "slug": "lip-balms",
        "id": 27,
        "name_keywords": [
            "lip balm",
            "lip butter",
            "lip care",
            "lip treatment",
            "tinted lip",
            "luscious lip balm",  # Aqualogica Plump+ naming
            "lip gloss",
            "lip oil",
            "lip serum",
            "lip liner",          # liner → lip-balms is a stretch but better than uncategorized
            "lip nourisher",      # Pixi "+Rose Lip Nourisher"
            "lip brightener",     # Pixi "+C Vit Lip Brightener"
            "lip treat",          # Laneige "Mini Lip Treats"
        ],
        "category_raw_keywords": [
            "lip balm",
            "lip care",
            "lip gloss",
            "lip colour",
            "lip color",
            # NOTE: bare "lip" intentionally omitted — too broad, would catch lip-masks/scrubs
        ],
        "exclude_fn": None,
    },
    # ── id=16  body-moisturizers ──────────────────────────────────────────────
    {
        "slug": "body-moisturizers",
        "id": 16,
        "name_keywords": [
            "body lotion",
            "body moisturizer",
            "body moisturiser",
            "body cream",
            "body butter",
            "body milk",
            "body milk lotion",
        ],
        "category_raw_keywords": [
            "body lotion",
            "body moisturizer",
            "body cream",
            "body butter",
            "body care",
        ],
        "exclude_fn": None,
    },
    # ── id=17  body-wash ──────────────────────────────────────────────────────
    {
        "slug": "body-wash",
        "id": 17,
        "name_keywords": [
            "body wash",
            "shower gel",
            "shower cream",
            "bath gel",
            "bath wash",
        ],
        "category_raw_keywords": [
            "body wash",
            "shower gel",
            "bath wash",
        ],
        "exclude_fn": None,
    },
    # ── id=18  body-scrubs ────────────────────────────────────────────────────
    {
        "slug": "body-scrubs",
        "id": 18,
        "name_keywords": [
            "body scrub",
            "body polish",
            "body exfoliator",
            "body exfoliating",
        ],
        "category_raw_keywords": [
            "body scrub",
            "body polish",
        ],
        "exclude_fn": None,
    },
    # ── id=19  body-oils ──────────────────────────────────────────────────────
    {
        "slug": "body-oils",
        "id": 19,
        "name_keywords": [
            "body oil",
            "massage oil",
            "stretch marks oil",
        ],
        "category_raw_keywords": [
            "body oil",
            "body oils",
        ],
        "exclude_fn": None,
    },
    # ── id=20  body-serums ────────────────────────────────────────────────────
    {
        "slug": "body-serums",
        "id": 20,
        "name_keywords": [
            "body serum",
        ],
        "category_raw_keywords": [
            "body serum",
        ],
        "exclude_fn": None,
    },
    # ── id=15  face-peels ─────────────────────────────────────────────────────
    {
        "slug": "face-peels",
        "id": 15,
        "name_keywords": [
            "chemical peel",
            "peel pad",
            "peel solution",
            "aha peel",
            "bha peel",
            "glycolic peel",
            # Spot correctors / targeted treatments — topical treatment category
            "spot corrector",
            "dark spot corrector",
            "acne spot corrector",
            # Acne treatment gels
            "acne treatment gel",
            "acne gel",
            "benzoyl peroxide gel",
            "benzoyl peroxide spot",
            "salicylic acid gel",
            "kojic acid gel",
            "kojic acid dark spot",
        ],
        "category_raw_keywords": [
            "peel",
            "peeling",
            "spot corrector",
            "acne treatment",
        ],
        "exclude_fn": None,
    },
    # ── id=21  hand-foot-care ─────────────────────────────────────────────────
    {
        "slug": "hand-foot-care",
        "id": 21,
        "name_keywords": [
            "hand cream",
            "hand lotion",
            "hand wash",
            "foot cream",
            "foot lotion",
            "foot scrub",
            "foot mask",
            "nail cream",
            "cuticle cream",
            "hand butter",
            "hand mask",
            "hand serum",
        ],
        "category_raw_keywords": [
            "hand cream",
            "hand care",
            "foot care",
            "hand & foot",
            "hand lotion",
        ],
        "exclude_fn": None,
    },
    # ── id=23  after-sun ──────────────────────────────────────────────────────
    {
        "slug": "after-sun",
        "id": 23,
        "name_keywords": [
            "after sun",
            "aftersun",
            "after-sun",
            "after sun lotion",
            "after sun gel",
            "soothing after sun",
            "detan face pack",       # de-tan = after-sun treatment category
            "detan pack",
            "de-tan pack",
            "de tan pack",
            "detanning",
            "de-tanning",
        ],
        "category_raw_keywords": [
            "after sun",
            "aftersun",
            "after-sun",
            "detan",
            "de-tan",
        ],
        "exclude_fn": None,
    },
    # ── id=25  eye-patches ────────────────────────────────────────────────────
    {
        "slug": "eye-patches",
        "id": 25,
        "name_keywords": [
            "eye patch",
            "eye patches",
            "under eye patch",
            "hydrogel patch",
            "hydrogel eye",
            "eye mask patch",
        ],
        "category_raw_keywords": [
            "eye patch",
            "eye patches",
            "hydrogel patch",
        ],
        "exclude_fn": None,
    },
    # ── id=26  under-eye-treatments ──────────────────────────────────────────
    {
        "slug": "under-eye-treatments",
        "id": 26,
        "name_keywords": [
            "under eye gel",
            "under eye treatment",
            "undereye treatment",
            "eye treatment",
            "eye contour",
            "puffy eyes",
        ],
        "category_raw_keywords": [
            "under eye",
            "eye treatment",
        ],
        "exclude_fn": None,
    },
    # ── id=27  lip-balms (already above) ─────────────────────────────────────
    # ── id=28  lip-scrubs ─────────────────────────────────────────────────────
    {
        "slug": "lip-scrubs",
        "id": 28,
        "name_keywords": [
            "lip scrub",
            "lip exfoliator",
            "lip exfoliating",
        ],
        "category_raw_keywords": [
            "lip scrub",
        ],
        "exclude_fn": None,
    },
    # ── id=29  lip-masks ──────────────────────────────────────────────────────
    {
        "slug": "lip-masks",
        "id": 29,
        "name_keywords": [
            "lip mask",
            "lip sleeping mask",
            "lip overnight mask",
            "lip sleeping",
        ],
        "category_raw_keywords": [
            "lip mask",
        ],
        "exclude_fn": None,
    },
    # ── id=30  shampoo-conditioner ────────────────────────────────────────────
    {
        "slug": "shampoo-conditioner",
        "id": 30,
        "name_keywords": [
            "shampoo",
            "hair conditioner",
            "hair rinse",
            "co-wash",
            "cowash",
        ],
        "category_raw_keywords": [
            "shampoo",
            "conditioner",
            "hair wash",
            "co-wash",
        ],
        "exclude_fn": None,
    },
    # ── id=31  hair-serums-oils ───────────────────────────────────────────────
    {
        "slug": "hair-serums-oils",
        "id": 31,
        "name_keywords": [
            "hair serum",
            "hair oil",
            "hair drops",
            "hair elixir",
            "scalp oil",
            "argan oil shots",
            "phytolipid oil shots",
            "post-wash hair balm",
            "post wash hair balm",
            "hair growth oil",
            "hair nourishing oil",
        ],
        "category_raw_keywords": [
            "hair serum",
            "hair oil",
            "hair oils",
            "hair serums",
        ],
        "exclude_fn": None,
    },
    # ── id=32  hair-masks ─────────────────────────────────────────────────────
    {
        "slug": "hair-masks",
        "id": 32,
        "name_keywords": [
            "hair mask",
            "hair pack",
            "deep conditioning mask",
            "deep conditioner",
            "hair treatment mask",
            "hair spa",
        ],
        "category_raw_keywords": [
            "hair mask",
            "hair pack",
            "deep conditioner",
        ],
        "exclude_fn": None,
    },
    # ── id=33  scalp-care ─────────────────────────────────────────────────────
    {
        "slug": "scalp-care",
        "id": 33,
        "name_keywords": [
            "scalp serum",
            "scalp tonic",
            "scalp treatment",
            "scalp scrub",
            "scalp mask",
            "hair scalp",
            "scalp care",
            "dandruff treatment",
            "anti-dandruff treatment",
        ],
        "category_raw_keywords": [
            "scalp",
            "scalp care",
            "scalp treatment",
        ],
        "exclude_fn": None,
    },
]


def _matches_rule(rule: dict, name_lower: str, cat_raw_lower: str | None) -> bool:
    """Return True if the product matches this rule's keywords."""
    # Check name keywords
    for kw in rule["name_keywords"]:
        if kw in name_lower:
            return True
    # Check category_raw keywords
    if cat_raw_lower:
        for kw in rule["category_raw_keywords"]:
            if kw in cat_raw_lower:
                return True
    return False


def _classify_product(canonical_name: str, category_raw: str | None) -> int | None:
    """
    Return the canonical category id for a product, or None if unclassifiable.
    Rules are evaluated in order; first match wins.
    """
    name_lower = f" {canonical_name.lower()} "
    cat_raw_lower = category_raw.lower() if category_raw else None

    for rule in CATEGORY_RULES:
        if not _matches_rule(rule, name_lower, cat_raw_lower):
            continue
        # Apply exclusion guard if present
        exclude_fn = rule.get("exclude_fn")
        if exclude_fn and exclude_fn(name_lower):
            continue
        return rule["id"]

    return None


async def _get_conn() -> psycopg.AsyncConnection:
    dsn = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)


async def run(dry_run: bool = False) -> None:
    conn = await _get_conn()

    # Fetch all unclassified products
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT p.id, p.canonical_name, p.category_raw
            FROM core.products p
            WHERE p.canonical_category_id IS NULL
            ORDER BY p.id
        """)
        products = await cur.fetchall()

    log.info("fetch_unclassified", count=len(products))

    # Classify each product
    assignments: list[tuple[int, int]] = []  # (product_id, category_id)
    unmatched: list[str] = []
    cat_counts: dict[str, int] = {}

    for p in products:
        cat_id = _classify_product(p["canonical_name"], p["category_raw"])
        if cat_id is not None:
            assignments.append((p["id"], cat_id))
            slug = next(r["slug"] for r in CATEGORY_RULES if r["id"] == cat_id)
            cat_counts[slug] = cat_counts.get(slug, 0) + 1
        else:
            unmatched.append(p["canonical_name"])

    log.info("classification_done",
             total_unclassified=len(products),
             will_assign=len(assignments),
             still_unmatched=len(unmatched))

    print(f"\n=== Assignment plan ===")
    print(f"  Products to assign: {len(assignments)}")
    print(f"  Products remaining unmatched: {len(unmatched)}")
    print(f"\n  By category:")
    for slug, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {slug:35s}: {cnt}")

    if dry_run:
        print("\n  [DRY RUN] — no DB writes made.")
        return

    # Apply updates in batches
    updated = 0
    async with conn.cursor() as cur:
        for product_id, cat_id in assignments:
            await cur.execute(
                """
                UPDATE core.products
                SET canonical_category_id = %s
                WHERE id = %s AND canonical_category_id IS NULL
                """,
                (cat_id, product_id),
            )
            updated += cur.rowcount

    await conn.commit()
    log.info("assignment_complete", updated=updated)
    print(f"\n  Committed {updated} updates to DB.")

    # Final summary
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT tc.slug, count(*) as cnt
            FROM core.products p
            JOIN taxonomy.categories tc ON tc.id = p.canonical_category_id
            GROUP BY tc.slug
            ORDER BY cnt DESC
        """)
        final_rows = await cur.fetchall()

    async with conn.cursor() as cur:
        await cur.execute("SELECT count(*) as cnt FROM core.products WHERE canonical_category_id IS NULL")
        still_null = (await cur.fetchone())["cnt"]

    print(f"\n=== Final DB state ===")
    for r in final_rows:
        print(f"  {r['slug']:35s}: {r['cnt']}")
    print(f"  {'(uncategorized)':35s}: {still_null}")

    await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign canonical_category_id via name/category_raw keywords")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be assigned without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
