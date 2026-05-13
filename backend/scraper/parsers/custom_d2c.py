"""Parse custom (non-Shopify) D2C brand product pages into ScrapedProduct.

Strategy priority:
  1. JSON-LD Product schema  — most reliable, used by Nathabit etc.
  2. Open Graph + product meta tags — Plix, many others
  3. URL-slug fallback — always produces a name; no price/image
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any
from urllib.parse import urlparse

from scraper.models import ScrapedProduct

# Matches <title>…</title>
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_custom_d2c(html: str, retailer_slug: str, source_url: str) -> ScrapedProduct:
    """Best-effort parse of a D2C product page into ScrapedProduct."""

    # --- Brand-specific parsers (most reliable) ---
    if retailer_slug == "thebodyshop_in":
        tbs = _parse_thebodyshop(html)
        if tbs.get("name"):
            return _from_dict(tbs, retailer_slug, source_url)

    if retailer_slug == "bioderma_in":
        bio = _parse_bioderma(html)
        if bio.get("name"):
            return _from_dict(bio, retailer_slug, source_url)

    # --- 1. Try JSON-LD ---
    product_ld = _extract_json_ld_product(html)
    if product_ld:
        return _from_json_ld(product_ld, retailer_slug, source_url)

    # --- 2. Try OG / product meta tags (skip generic site titles) ---
    og = _extract_og_tags(html)
    title = og.get("title", "")
    # Reject generic site-level titles (no product-specific info)
    is_generic = not og.get("price") and (
        "telehealth" in title.lower() or
        "platform" in title.lower() or
        len(title) < 8
    )
    if og.get("title") and not is_generic:
        return _from_og(og, retailer_slug, source_url)

    # --- 3. Slug fallback: name from URL path ---
    name = _name_from_url(source_url)
    missing = {"current_price", "images", "brand_name", "category_hint", "rating"}
    return ScrapedProduct(
        retailer_slug=retailer_slug,
        source_url=source_url,
        canonical_name=name,
        brand_name=None,
        category_hint=None,
        current_price=None,
        compare_at_price=None,
        stock_status_raw=None,
        images=[],
        description_source="product_page_scrape",
        missing_fields=missing,
    )


# ---------------------------------------------------------------------------
# JSON-LD path
# ---------------------------------------------------------------------------

def _from_json_ld(product: dict[str, Any], retailer_slug: str, source_url: str) -> ScrapedProduct:
    missing: set[str] = set()

    canonical_name = product.get("name") or None
    if not canonical_name:
        missing.add("canonical_name")

    brand_raw = product.get("brand")
    if isinstance(brand_raw, dict):
        brand_name = brand_raw.get("name")
    elif isinstance(brand_raw, str):
        brand_name = brand_raw
    else:
        brand_name = None
    if not brand_name:
        missing.add("brand_name")

    parsed = urlparse(source_url)
    img_base = f"{parsed.scheme}://{parsed.netloc}"
    images = _extract_images_ld(product, img_base)
    if not images:
        missing.add("images")

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    current_price: float | None = None
    compare_at_price: float | None = None
    stock_status_raw: str | None = None
    if isinstance(offers, dict):
        # Try offers.price, then offers.lowPrice (AggregateOffer), then top-level price
        raw_price = offers.get("price") or offers.get("lowPrice") or product.get("price")
        try:
            current_price = float(raw_price) if raw_price is not None else None
        except (TypeError, ValueError):
            pass
        avail = offers.get("availability") or ""
        if avail:
            stock_status_raw = avail.rsplit("/", 1)[-1]
        raw_high = offers.get("highPrice")
        if raw_high is not None:
            try:
                hp = float(raw_high)
                if current_price and hp > current_price:
                    compare_at_price = hp
            except (TypeError, ValueError):
                pass
    if current_price is None:
        # Fallback: top-level price field (e.g. Kama Ayurveda JSON-LD)
        raw_price = product.get("price")
        try:
            current_price = float(raw_price) if raw_price is not None else None
        except (TypeError, ValueError):
            pass
    if not current_price:
        missing.add("current_price")

    rating_raw: str | None = None
    agg = product.get("aggregateRating")
    if isinstance(agg, dict):
        rv = agg.get("ratingValue")
        rc = agg.get("ratingCount") or agg.get("reviewCount")
        if rv and rc:
            rating_raw = f"{rv} ({rc})"
    if not rating_raw:
        missing.add("rating")

    description_raw = product.get("description") or None

    # additionalProperty — some brands embed skin type, concerns, size, origin as structured data
    pack_size: str | None = None
    skin_type: list[str] = []
    skin_concerns: list[str] = []
    country_of_origin: str | None = None
    claims: list[str] = []
    for prop in product.get("additionalProperty") or []:
        if not isinstance(prop, dict):
            continue
        name_lc = (prop.get("name") or "").lower()
        val = prop.get("value") or prop.get("unitText") or ""
        if not val:
            continue
        if "skin type" in name_lc or "skin_type" in name_lc:
            skin_type = [s.strip() for s in str(val).split(",") if s.strip()]
        elif "concern" in name_lc:
            skin_concerns = [s.strip() for s in str(val).split(",") if s.strip()]
        elif "size" in name_lc or "volume" in name_lc or "weight" in name_lc or "net " in name_lc:
            pack_size = str(val)
        elif "country" in name_lc or "origin" in name_lc:
            country_of_origin = str(val)
        elif "claim" in name_lc or "certif" in name_lc or "free" in name_lc:
            claims.append(str(val))

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
        pack_size=pack_size,
        skin_type=skin_type,
        skin_concerns=skin_concerns,
        country_of_origin=country_of_origin,
        claims=claims,
        missing_fields=missing,
    )


def _extract_json_ld_product(html: str) -> dict[str, Any] | None:
    for block in re.finditer(
        r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>",
        html, flags=re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1).strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return None


def _extract_images_ld(product: dict[str, Any], base_url: str = "") -> list[str]:
    img = product.get("image")
    if isinstance(img, str):
        imgs = [img]
    elif isinstance(img, list):
        imgs = [i for i in img if isinstance(i, str)]
    else:
        return []
    if base_url:
        return [f"{base_url}{i}" if i.startswith("/") else i for i in imgs]
    return imgs


# ---------------------------------------------------------------------------
# OG / product meta path
# ---------------------------------------------------------------------------

def _from_og(og: dict[str, str], retailer_slug: str, source_url: str) -> ScrapedProduct:
    missing: set[str] = set()

    canonical_name = og.get("title") or _name_from_url(source_url)
    brand_name = og.get("brand") or og.get("site_name") or None
    if not brand_name:
        missing.add("brand_name")

    images = [og["image"]] if og.get("image") else []
    if not images:
        missing.add("images")

    current_price: float | None = None
    if og.get("price"):
        try:
            current_price = float(og["price"])
        except ValueError:
            pass
    if not current_price:
        missing.add("current_price")

    missing.update({"rating", "category_hint"})

    return ScrapedProduct(
        retailer_slug=retailer_slug,
        source_url=source_url,
        canonical_name=canonical_name,
        brand_name=brand_name,
        category_hint=None,
        current_price=current_price,
        compare_at_price=None,
        stock_status_raw=None,
        images=images,
        description_source="product_page_scrape",
        pack_size=og.get("pack_size"),
        missing_fields=missing,
    )


def _extract_og_tags(html: str) -> dict[str, str]:
    """Extract og: and product: meta tags."""
    tags: dict[str, str] = {}
    for m in re.finditer(
        r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    ):
        prop, content = m.group(1).lower(), html_lib.unescape(m.group(2)).strip()
        if prop == "og:title":
            tags["title"] = content
        elif prop == "og:image":
            tags["image"] = content
        elif prop == "og:site_name":
            tags["site_name"] = content
        elif prop == "product:price:amount":
            tags["price"] = content
        elif prop == "product:brand":
            tags["brand"] = content
    return tags


# ---------------------------------------------------------------------------
# The Body Shop India — Next.js __NEXT_DATA__ / initialState / productDetailReducer
# ---------------------------------------------------------------------------

_TBS_CDN = "https://media.thebodyshop.in/media/catalog/product"


def _parse_thebodyshop(html: str) -> dict[str, Any]:
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
        product = (
            data["props"]["pageProps"]["initialState"]
            ["productDetailReducer"]["product"]
        )
        if isinstance(product, list):
            product = product[0] if product else {}
    except (KeyError, json.JSONDecodeError, TypeError):
        return {}

    images: list[str] = []
    for img in product.get("image") or []:
        if isinstance(img, dict) and img.get("file"):
            images.append(f"{_TBS_CDN}{img['file']}")

    category_hint: str | None = None
    cat = product.get("categoryData")
    if isinstance(cat, dict):
        child = cat.get("child_category")
        category_hint = (child or cat).get("name")

    avg = product.get("avgRating")
    cnt = product.get("ratingCount")
    rating_raw = f"{avg} ({cnt})" if avg and cnt else None

    price = product.get("price")
    in_stock = product.get("isInStock")

    return {
        "name": product.get("name"),
        "price": float(price) if price else None,
        "images": images,
        "category_hint": category_hint,
        "rating_raw": rating_raw,
        "stock_status_raw": "InStock" if in_stock else ("OutOfStock" if in_stock is False else None),
    }


def _from_dict(data: dict[str, Any], retailer_slug: str, source_url: str) -> ScrapedProduct:
    missing: set[str] = set()
    if not data.get("price"):
        missing.add("current_price")
    if not data.get("images"):
        missing.add("images")
    if not data.get("category_hint"):
        missing.add("category_hint")
    if not data.get("rating_raw"):
        missing.add("rating")
    missing.add("brand_name")
    return ScrapedProduct(
        retailer_slug=retailer_slug,
        source_url=source_url,
        canonical_name=data.get("name"),
        brand_name=None,
        category_hint=data.get("category_hint"),
        current_price=data.get("price"),
        compare_at_price=None,
        stock_status_raw=data.get("stock_status_raw"),
        images=data.get("images") or [],
        description_source="product_page_scrape",
        rating_raw=data.get("rating_raw"),
        pack_size=data.get("pack_size"),
        skin_type=data.get("skin_type") or [],
        skin_concerns=data.get("skin_concerns") or [],
        country_of_origin=data.get("country_of_origin"),
        key_ingredients_raw=data.get("key_ingredients_raw"),
        claims=data.get("claims") or [],
        missing_fields=missing,
    )


# ---------------------------------------------------------------------------
# Bioderma India — Drupal site, no JSON-LD/OG: H1 name + product image paths
# ---------------------------------------------------------------------------

_BIODERMA_BASE = "https://www.bioderma-india.in"
# Use product_packshot_slider style — main product images (front/back pack shots)
_BIODERMA_IMG_RE = re.compile(
    r'src=["\']([^"\']*sites/in/files/styles/product_packshot_slider/public/products/[^"\']+)["\']',
    re.IGNORECASE,
)


def _parse_bioderma(html: str) -> dict[str, Any]:
    name_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    name = None
    if name_m:
        raw = re.sub(r"<[^>]+>", "", name_m.group(1))
        name = " ".join(raw.split()) or None

    images: list[str] = []
    seen: set[str] = set()
    for m in _BIODERMA_IMG_RE.finditer(html):
        url = m.group(1)
        if url.startswith("/"):
            url = f"{_BIODERMA_BASE}{url}"
        if url not in seen:
            seen.add(url)
            images.append(url)

    return {"name": name, "images": images}


# ---------------------------------------------------------------------------
# URL slug fallback
# ---------------------------------------------------------------------------

def _name_from_url(url: str) -> str:
    """Turn the last meaningful path segment into a title-cased product name."""
    # Strip query string and trailing slash
    path = re.sub(r"\?.*$", "", url).rstrip("/")
    # Take last path segment; for Plix URLs like /product/name/123 skip numeric tail
    segments = [s for s in path.split("/") if s and not s.isdigit()]
    slug = segments[-1] if segments else "Unknown Product"
    # Convert slug to name: replace hyphens/underscores with spaces, title-case
    name = re.sub(r"[-_]+", " ", slug)
    # Remove leading digits like "6-niacinamide" → keep "6 Niacinamide"
    return name.title()
