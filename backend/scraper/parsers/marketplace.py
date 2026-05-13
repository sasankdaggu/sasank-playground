"""Parse marketplace HTML pages into ScrapedProduct."""
from __future__ import annotations

import json
import re
from typing import Any

from scraper.models import ScrapedProduct


def parse_marketplace_html(html: str, retailer_slug: str, source_url: str) -> ScrapedProduct:
    if retailer_slug == "tira":
        return _parse_tira(html, source_url)
    return _parse_json_ld(html, retailer_slug, source_url)


# ---------------------------------------------------------------------------
# CDN image extraction — all galleries are embedded in static HTML
# ---------------------------------------------------------------------------

def _extract_nykaa_images(html: str) -> list[str]:
    """Extract full-size gallery images from Nykaa's CDN URLs."""
    all_urls = re.findall(
        r'https://images-static\.nykaa\.com/media/catalog/product/[^\s"\'<>]+\.jpg',
        html,
    )
    raw = [u for u in all_urls if "/tr:" not in u]
    return list(dict.fromkeys(raw))


def _extract_purplle_images(html: str) -> list[str]:
    """Extract 750px gallery images from Purplle's CDN (ppl-media.com)."""
    all_urls = re.findall(
        r'https://media6\.ppl-media\.com/[^\s"\'<>]+\.jpg',
        html,
    )
    hires = [u for u in all_urls if "h-750" in u and "f-avif" not in u]
    return list(dict.fromkeys(hires))


# ---------------------------------------------------------------------------
# HTML section extraction helpers (Nykaa and similar structured pages)
# ---------------------------------------------------------------------------

def _extract_html_section(html: str, section_id: str) -> str | None:
    """Extract text from <section id="section_id">...</section>."""
    pattern = f'<section[^>]*id=(?:\'|"){re.escape(section_id)}(?:\'|")[^>]*>(.*?)</section>'
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _extract_nykaa_description(html: str) -> str | None:
    """Extract product description from Nykaa's HTML (falls back to JSON-LD)."""
    # Nykaa renders description in a div with data-at="product-desc" or similar
    for pat in [
        r'data-at=["\']product-desc["\'][^>]*>(.*?)</div>',
        r'class=["\'][^"\']*productDesc[^"\']*["\'][^>]*>(.*?)</div>',
    ]:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            text = re.sub(r"<[^>]+>", " ", m.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            if text and len(text) > 20:
                return text
    return None


# ---------------------------------------------------------------------------
# Tira — Fynd platform (window.APP_DATA)
# ---------------------------------------------------------------------------

def _parse_tira(html: str, source_url: str) -> ScrapedProduct:
    missing: set[str] = set()
    data = _extract_fynd_app_data(html)

    for field in ("canonical_name", "brand_name", "current_price", "images"):
        if not data.get(field):
            missing.add(field)
    if not data.get("category_hint"):
        missing.add("category_hint")
    if not data.get("rating_raw"):
        missing.add("rating")
    if not data.get("ingredients_raw"):
        missing.add("ingredients")

    return ScrapedProduct(
        retailer_slug="tira",
        source_url=source_url,
        canonical_name=data.get("canonical_name"),
        brand_name=data.get("brand_name"),
        category_hint=data.get("category_hint"),
        current_price=data.get("current_price"),
        compare_at_price=data.get("compare_at_price"),
        stock_status_raw=data.get("stock_status_raw"),
        images=data.get("images") or [],
        description_raw=data.get("description_raw"),
        description_source="product_page_scrape",
        rating_raw=data.get("rating_raw"),
        ingredients_raw=data.get("ingredients_raw"),
        pack_size=data.get("pack_size"),
        how_to_use=data.get("how_to_use"),
        skin_type=data.get("skin_type") or [],
        skin_concerns=data.get("skin_concerns") or [],
        country_of_origin=data.get("country_of_origin"),
        key_ingredients_raw=data.get("key_ingredients_raw"),
        claims=data.get("claims") or [],
        missing_fields=missing,
    )


def _extract_fynd_app_data(html: str) -> dict[str, Any]:
    marker = "window.APP_DATA = {"
    start = html.find(marker)
    if start < 0:
        return {}
    end = html.find("</script>", start)
    raw = html[start + len(marker) - 1: end].strip().rstrip(";")
    try:
        app_data = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    pd = app_data.get("reduxData", {}).get("catalog", {}).get("product_details", {})
    if not pd:
        return {}

    attrs = pd.get("attributes", {}) if isinstance(pd.get("attributes"), dict) else {}
    images = [
        m["url"] for m in pd.get("medias", [])
        if isinstance(m, dict) and m.get("type") == "image" and m.get("url")
    ]
    cats = pd.get("categories", [])
    category_hint = cats[0]["name"] if cats and isinstance(cats[0], dict) else None
    rating_val = pd.get("rating")
    rating_cnt = pd.get("rating_count")
    rating_raw = f"{rating_val} ({rating_cnt})" if rating_val and rating_val > 0 else None
    price = attrs.get("min_price_effective")
    mrp = attrs.get("price") or attrs.get("mrp")
    is_available = attrs.get("is_available")

    # Extended fields from Fynd APP_DATA
    pack_size = (
        pd.get("net_quantity")
        or attrs.get("net_quantity")
        or attrs.get("pack_size")
        or attrs.get("volume")
    )
    country_of_origin = pd.get("country_of_origin") or attrs.get("country_of_origin")

    # Highlights — Fynd stores how-to-use / key features as a list of bullet strings
    highlights = pd.get("highlights") or []
    how_to_use: str | None = None
    key_ingredients_raw: str | None = None
    for h in highlights:
        hl = h.lower() if isinstance(h, str) else ""
        if "how to use" in hl or "apply" in hl or "usage" in hl:
            how_to_use = h
        elif "ingredient" in hl or "activ" in hl:
            key_ingredients_raw = h

    # Full ingredients and skin attributes from custom_order or attributes
    ingredients_raw = (
        attrs.get("ingredients")
        or attrs.get("full_ingredients")
        or pd.get("ingredients")
    )

    raw_skin_type = attrs.get("skin_type") or attrs.get("suitable_for")
    skin_type: list[str] = []
    if isinstance(raw_skin_type, list):
        skin_type = [s for s in raw_skin_type if isinstance(s, str)]
    elif isinstance(raw_skin_type, str) and raw_skin_type:
        skin_type = [s.strip() for s in raw_skin_type.split(",") if s.strip()]

    raw_concerns = attrs.get("skin_concern") or attrs.get("concerns") or attrs.get("skin_concerns")
    skin_concerns: list[str] = []
    if isinstance(raw_concerns, list):
        skin_concerns = [s for s in raw_concerns if isinstance(s, str)]
    elif isinstance(raw_concerns, str) and raw_concerns:
        skin_concerns = [s.strip() for s in raw_concerns.split(",") if s.strip()]

    tags = pd.get("tags") or []
    claims = [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []

    return {
        "canonical_name": pd.get("name"),
        "brand_name": attrs.get("brand_name") or attrs.get("brand"),
        "current_price": float(price) if price else None,
        "compare_at_price": float(mrp) if mrp and mrp != price else None,
        "stock_status_raw": "InStock" if is_available else ("OutOfStock" if is_available is False else None),
        "description_raw": pd.get("description"),
        "images": images,
        "category_hint": category_hint,
        "rating_raw": rating_raw,
        "ingredients_raw": ingredients_raw,
        "pack_size": str(pack_size) if pack_size else None,
        "how_to_use": how_to_use,
        "skin_type": skin_type,
        "skin_concerns": skin_concerns,
        "country_of_origin": country_of_origin,
        "key_ingredients_raw": key_ingredients_raw,
        "claims": claims,
    }


# ---------------------------------------------------------------------------
# Generic JSON-LD parser (Nykaa, Purplle, Amazon)
# ---------------------------------------------------------------------------

_INGREDIENTS_RE = re.compile(
    r'<section[^>]*id=["\']ingredients["\'][^>]*>(.*?)</section>',
    re.IGNORECASE | re.DOTALL,
)
_KEY_INGREDIENTS_RE = re.compile(
    r'<section[^>]*id=["\']key-ingredients["\'][^>]*>(.*?)</section>',
    re.IGNORECASE | re.DOTALL,
)
_HOW_TO_USE_RE = re.compile(
    r'<section[^>]*id=["\']how-to-use["\'][^>]*>(.*?)</section>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(html_snippet: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_snippet)
    return re.sub(r"\s+", " ", text).strip()


def _parse_json_ld(html: str, retailer_slug: str, source_url: str) -> ScrapedProduct:
    missing: set[str] = set()
    products = _extract_json_ld_products(html)
    product = products[0] if products else {}

    canonical_name = product.get("name") or None
    brand_raw = product.get("brand")
    if isinstance(brand_raw, dict):
        brand_name = brand_raw.get("name")
    elif isinstance(brand_raw, str):
        brand_name = brand_raw
    else:
        brand_name = None

    images = _extract_images(product)
    if retailer_slug == "nykaa":
        cdn = _extract_nykaa_images(html)
        if cdn:
            images = cdn
    elif retailer_slug == "purplle":
        cdn = _extract_purplle_images(html)
        if cdn:
            images = cdn
        elif len(images) <= 1:
            next_images = _parse_purplle_next_data(html)
            if next_images:
                images = next_images

    current_price: float | None = None
    compare_at_price: float | None = None
    stock_status_raw: str | None = None
    offers_obj = product.get("offers")
    if isinstance(offers_obj, dict):
        raw_price = offers_obj.get("price")
        if raw_price is not None:
            try:
                current_price = float(raw_price)
            except (TypeError, ValueError):
                pass
        raw_high = offers_obj.get("highPrice")
        if raw_high is not None:
            try:
                hp = float(raw_high)
                if current_price and hp > current_price:
                    compare_at_price = hp
            except (TypeError, ValueError):
                pass
        availability = offers_obj.get("availability")
        if isinstance(availability, str):
            stock_status_raw = availability.rsplit("/", 1)[-1]

    rating_raw: str | None = None
    agg = product.get("aggregateRating")
    if isinstance(agg, dict):
        rv = agg.get("ratingValue")
        rc = agg.get("ratingCount") or agg.get("reviewCount")
        if rv is not None and rc is not None:
            rating_raw = f"{rv} ({rc})"

    # Description — JSON-LD description field (Nykaa includes it)
    description_raw: str | None = product.get("description") or None
    if not description_raw and retailer_slug == "nykaa":
        description_raw = _extract_nykaa_description(html)

    # Ingredients from dedicated HTML section
    ingredients_raw: str | None = None
    m = _INGREDIENTS_RE.search(html)
    if m:
        ingredients_raw = _strip_tags(m.group(1)) or None

    # Key ingredients section
    key_ingredients_raw: str | None = None
    km = _KEY_INGREDIENTS_RE.search(html)
    if km:
        key_ingredients_raw = _strip_tags(km.group(1)) or None

    # How to use section
    how_to_use: str | None = None
    hm = _HOW_TO_USE_RE.search(html)
    if hm:
        how_to_use = _strip_tags(hm.group(1)) or None

    for field_name, val in [
        ("canonical_name", canonical_name), ("brand_name", brand_name),
        ("current_price", current_price), ("stock_status", stock_status_raw),
        ("rating", rating_raw),
    ]:
        if not val:
            missing.add(field_name)
    if not images:
        missing.add("images")
    if not ingredients_raw:
        missing.add("ingredients")
    missing.add("category_hint")

    return ScrapedProduct(
        retailer_slug=retailer_slug,
        source_url=source_url,
        canonical_name=canonical_name,
        brand_name=brand_name,
        category_hint=None,
        current_price=current_price,
        compare_at_price=compare_at_price,
        stock_status_raw=stock_status_raw,
        images=images,
        description_raw=description_raw,
        description_source="product_page_scrape",
        rating_raw=rating_raw,
        ingredients_raw=ingredients_raw,
        key_ingredients_raw=key_ingredients_raw,
        how_to_use=how_to_use,
        missing_fields=missing,
    )


def _extract_json_ld_products(html: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, flags=re.DOTALL | re.IGNORECASE,
    ):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                products.append(item)
    return products


def _extract_images(product: dict[str, Any]) -> list[str]:
    img = product.get("image")
    if isinstance(img, str):
        return [img]
    if isinstance(img, list):
        return [i for i in img if isinstance(i, str)]
    return []


def _parse_purplle_next_data(html: str) -> list[str]:
    marker = "window.__NEXT_DATA__"
    start = html.find(marker)
    if start < 0:
        return []
    eq = html.find("=", start)
    end = html.find("</script>", eq)
    raw = html[eq + 1: end].strip().rstrip(";")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    try:
        props = data.get("props", {}).get("pageProps", {})
        product = props.get("productDetails") or props.get("product") or {}
        imgs = product.get("images") or product.get("image_urls") or []
        if isinstance(imgs, list):
            return [i if isinstance(i, str) else i.get("url", "") for i in imgs if i]
    except Exception:
        pass
    return []
