"""Parse Nykaa product pages into ScrapedProduct.

Primary data source: window.__PRELOADED_STATE__.productPage.product (Redux state)
Fallback: application/ld+json Product schema
"""
from __future__ import annotations

import html as _html_lib
import json
import re
from typing import Any

from scraper.models import ScrapedProduct, ScrapedVariant

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def parse_nykaa_product(html: str, url: str) -> ScrapedProduct:
    """Parse a Nykaa product page. Returns ScrapedProduct with all available fields."""
    state = _preloaded_state(html)
    product = (state.get("productPage") or {}).get("product") or {}

    if product:
        return _from_redux(product, url)

    # Fallback: JSON-LD
    ld = _json_ld_product(html)
    if ld:
        return _from_json_ld(ld, url)

    return ScrapedProduct(
        retailer_slug="nykaa", source_url=url,
        canonical_name=None, brand_name=None, category_hint=None,
        current_price=None, compare_at_price=None, stock_status_raw=None,
        missing_fields={"name", "price", "brand"},
    )


# ── Redux parser ──────────────────────────────────────────────────────────────

def _from_redux(p: dict, url: str) -> ScrapedProduct:
    name = _clean(p.get("name") or "")
    brand = _clean(p.get("brandName") or "")

    # Price: use the parent mrp/offerPrice (represents the default variant)
    mrp = _float(p.get("mrp"))
    offer = _float(p.get("offerPrice"))

    # Stock
    stock_raw = "InStock" if p.get("inStock") else "OutOfStock"

    # Images: parentMedia array
    images = [
        m["url"] for m in (p.get("parentMedia") or [])
        if isinstance(m, dict) and m.get("mediaType") == "image" and m.get("url")
    ]

    # Variants
    variants = _parse_variants(p.get("variants") or [])

    # Category: primaryCategories gives l1/l2/l3 with names
    primary_cats = p.get("primaryCategories") or {}
    cat_l1 = (primary_cats.get("l1") or {}).get("name") or None
    cat_l3 = (primary_cats.get("l3") or {}).get("name") or None
    # Also try metaKeywords: "Name,L1,L2,L3"
    if not cat_l1:
        meta_kw = p.get("metaKeywords") or ""
        parts = [x.strip() for x in meta_kw.split(",") if x.strip()]
        if len(parts) >= 2:
            cat_l1 = parts[1]
        if len(parts) >= 4 and not cat_l3:
            cat_l3 = parts[-1]

    # Description: strip HTML
    description = _strip_html(p.get("description") or "")

    # Ingredients: "Key Ingredients" HTML section — store as key_ingredients_raw
    ingredients_html = p.get("ingredients") or ""
    key_ingredients = _strip_html(ingredients_html)

    # How to use
    how_to_use = _strip_html(p.get("howToUse") or "")

    # Full INCI: Nykaa puts the full ingredient list in the HTML page outside Redux.
    # We store key_ingredients_raw and let the ingredient extraction queue handle INCI.

    # Country
    country = _clean(p.get("originOfCountryName") or p.get("countryOfManufacture") or "")

    # Rating
    rating = p.get("rating")
    rating_count = p.get("ratingCount")
    rating_raw = f"{rating} ({rating_count})" if rating and rating_count else None

    # Pack size from first in-stock variant, or first variant
    pack_size = _pick_pack_size(p.get("variants") or [])

    # Source URL: prefer product slug
    slug = p.get("slug") or ""
    if slug and not url.endswith(slug):
        source_url = f"https://www.nykaa.com/{slug.lstrip('/')}"
    else:
        source_url = url

    missing: set[str] = set()
    if not name:
        missing.add("name")
    if offer is None:
        missing.add("price")

    return ScrapedProduct(
        retailer_slug="nykaa",
        source_url=source_url,
        canonical_name=name or None,
        brand_name=brand or None,
        category_hint=cat_l1,
        subcategory_hint=cat_l3,
        current_price=offer,
        compare_at_price=mrp if mrp != offer else None,
        stock_status_raw=stock_raw,
        variants=variants,
        images=images,
        description_raw=description or None,
        description_source="nykaa" if description else None,
        rating_raw=rating_raw,
        pack_size=pack_size,
        how_to_use=how_to_use or None,
        key_ingredients_raw=key_ingredients or None,
        country_of_origin=country or None,
        source_tags=["nykaa"],
        missing_fields=missing,
    )


def _parse_variants(raw: list) -> list[ScrapedVariant]:
    variants = []
    for v in raw:
        if not isinstance(v, dict):
            continue
        variants.append(ScrapedVariant(
            sku=v.get("sku"),
            option_value=v.get("packSize") or v.get("variantName"),
            price=_float(v.get("offerPrice")),
            compare_at_price=_float(v.get("mrp")),
            available=bool(v.get("inStock")),
        ))
    return variants


def _pick_pack_size(variants: list) -> str | None:
    for v in variants:
        if isinstance(v, dict) and v.get("inStock") and v.get("packSize"):
            return v["packSize"]
    for v in variants:
        if isinstance(v, dict) and v.get("packSize"):
            return v["packSize"]
    return None


# ── JSON-LD fallback ──────────────────────────────────────────────────────────

def _from_json_ld(ld: dict, url: str) -> ScrapedProduct:
    offers = ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = _float(offers.get("price"))
    availability = offers.get("availability") or ""
    stock_raw = "InStock" if "InStock" in availability else "OutOfStock"
    rating_obj = ld.get("aggregateRating") or {}
    rating_val = rating_obj.get("ratingValue")
    rating_cnt = rating_obj.get("reviewCount")
    rating_raw = f"{rating_val} ({rating_cnt})" if rating_val else None
    images = ld.get("image") or []
    if isinstance(images, str):
        images = [images]
    return ScrapedProduct(
        retailer_slug="nykaa",
        source_url=url,
        canonical_name=_clean(ld.get("name") or ""),
        brand_name=_clean(str(ld.get("brand") or "")),
        category_hint=None,
        current_price=price,
        compare_at_price=None,
        stock_status_raw=stock_raw,
        images=images,
        rating_raw=rating_raw,
        description_raw=_clean(ld.get("description") or "") or None,
        description_source="nykaa",
        source_tags=["nykaa"],
    )


# ── HTML extraction helpers ───────────────────────────────────────────────────

def _preloaded_state(html: str) -> dict:
    idx = html.find("window.__PRELOADED_STATE__")
    if idx < 0:
        return {}
    try:
        start = html.index("{", idx)
        end = html.find("</script>", start)
        return json.loads(html[start:end].rstrip("; \n"))
    except (ValueError, json.JSONDecodeError):
        return {}


def _json_ld_product(html: str) -> dict | None:
    """Extract first Product JSON-LD from the page."""
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
            elif isinstance(data, dict) and data.get("@type") == "Product":
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = _html_lib.unescape(text)
    text = _TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _clean(text: str) -> str:
    return _html_lib.unescape(text).strip()


def _float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
