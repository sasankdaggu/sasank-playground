"""Parse Shopify /products.json response into ScrapedProduct list."""
from __future__ import annotations

import re
import json
from typing import Any

from scraper.models import ScrapedProduct, ScrapedVariant

# Shopify product tags that map to structured claims
_CLAIM_KEYWORDS: frozenset[str] = frozenset({
    "vegan", "cruelty-free", "cruelty free", "fragrance-free", "fragrance free",
    "paraben-free", "paraben free", "sulfate-free", "sulfate free",
    "alcohol-free", "alcohol free", "dermatologist tested", "dermatologist-tested",
    "hypoallergenic", "non-comedogenic", "non comedogenic",
    "organic", "natural", "clean beauty", "mineral sunscreen",
    "reef-safe", "reef safe", "microbiome-friendly", "microbiome friendly",
})
_CLAIM_FRAGMENTS: tuple[str, ...] = ("spf", "cruelty", "fragrance", "paraben", "sulfate", "free from")

# Option names that indicate a size/volume dimension
_SIZE_OPTION_NAMES: frozenset[str] = frozenset({
    "size", "volume", "pack size", "weight", "net weight", "quantity", "pack"
})
_SIZE_RE = re.compile(r'\d+\s*(?:ml|g|gm|mg|oz|fl oz|l|kg|mL|L)', re.IGNORECASE)


def parse_shopify_json(raw_json: str, retailer_slug: str, base_url: str) -> list[ScrapedProduct]:
    payload = json.loads(raw_json)
    products = payload.get("products", [])
    return [_parse_one(p, retailer_slug, base_url) for p in products]


def _parse_one(p: dict[str, Any], retailer_slug: str, base_url: str) -> ScrapedProduct:
    missing: set[str] = set()

    canonical_name = p.get("title") or None
    if not canonical_name:
        missing.add("canonical_name")

    brand_name = None  # set from retailer.name in db.py; vendor field is unreliable
    category_hint = p.get("product_type") or None
    if not category_hint:
        missing.add("category_hint")

    description_raw = p.get("body_html") or None
    if not description_raw:
        missing.add("description")

    images = [img["src"] for img in (p.get("images") or []) if img.get("src")]
    if not images:
        missing.add("images")

    variants_raw = p.get("variants") or []
    variants = [
        ScrapedVariant(
            sku=v.get("sku") or None,
            option_value=None if v.get("title") == "Default Title" else v.get("title"),
            price=float(v["price"]) if v.get("price") else None,
            compare_at_price=float(v["compare_at_price"]) if v.get("compare_at_price") else None,
            available=v.get("available"),
        )
        for v in variants_raw
    ]

    first = variants[0] if variants else None
    current_price = first.price if first else None
    compare_at_price = first.compare_at_price if first else None
    if current_price is None:
        missing.add("current_price")

    missing.add("ingredients")
    missing.add("rating")

    stock_status_raw = (
        "in_stock" if any(v.get("available") for v in variants_raw) else "out_of_stock"
    )

    # Pack size — prefer an explicit size/volume option; fall back to variant title if size-like
    pack_size: str | None = None
    options = p.get("options") or []
    size_opt = next(
        (o for o in options if o.get("name", "").lower().strip() in _SIZE_OPTION_NAMES),
        None,
    )
    if size_opt and size_opt.get("values"):
        pack_size = size_opt["values"][0]
    elif variants and variants[0].option_value:
        val = variants[0].option_value
        if val and _SIZE_RE.search(val):
            pack_size = val

    # Claims from Shopify product tags (comma-separated string)
    raw_tags = p.get("tags") or ""
    tag_list = [t.strip() for t in (raw_tags.split(",") if isinstance(raw_tags, str) else raw_tags) if t.strip()]
    claims: list[str] = []
    for tag in tag_list:
        tl = tag.lower()
        if tl in _CLAIM_KEYWORDS or any(frag in tl for frag in _CLAIM_FRAGMENTS):
            claims.append(tag)

    # Capture full unfiltered tag list for downstream use
    source_tags: list[str] | None = tag_list if tag_list else None

    return ScrapedProduct(
        retailer_slug=retailer_slug,
        source_url=f"{base_url}/products/{p.get('handle', '')}",
        canonical_name=canonical_name,
        brand_name=brand_name,
        category_hint=category_hint,
        current_price=current_price,
        compare_at_price=compare_at_price,
        stock_status_raw=stock_status_raw,
        variants=variants,
        images=images,
        description_raw=description_raw,
        description_source="shopify_body_html",
        pack_size=pack_size,
        claims=claims,
        source_tags=source_tags,
        missing_fields=missing,
    )
