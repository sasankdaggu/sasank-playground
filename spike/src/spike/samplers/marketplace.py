from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from spike.config import retailer_by_slug
from spike.models import ParsedSample, RawCapture
from spike.samplers.base import persist_parsed, persist_raw

log = structlog.get_logger()
_FETCHER_VERSION = "spike-marketplace-0.0.1"


def _json_ld_products(html: str) -> list[dict[str, Any]]:
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


def _extract_json_ld_images(product: dict[str, Any]) -> list[str]:
    """Extract all images from a JSON-LD product — handles string or array."""
    img_field = product.get("image")
    if isinstance(img_field, str):
        return [img_field]
    if isinstance(img_field, list):
        return [i for i in img_field if isinstance(i, str)]
    return []


def _parse_purplle_next_data(html: str) -> list[str]:
    """Extract full image gallery from Purplle's __NEXT_DATA__ JSON blob."""
    marker = "window.__NEXT_DATA__"
    start = html.find(marker)
    if start < 0:
        return []
    eq = html.find("=", start)
    if eq < 0:
        return []
    end = html.find("</script>", eq)
    raw = html[eq + 1: end].strip().rstrip(";")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    # Purplle: props.pageProps.productDetails.images or similar paths
    try:
        props = data.get("props", {}).get("pageProps", {})
        product = props.get("productDetails") or props.get("product") or {}
        imgs = product.get("images") or product.get("image_urls") or []
        if isinstance(imgs, list):
            return [i if isinstance(i, str) else i.get("url", "") for i in imgs if i]
    except Exception:
        pass
    return []


_OFFER_PATTERN = re.compile(
    r'<span[^>]*class=["\']offer["\'][^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL
)
_INGREDIENTS_PATTERN = re.compile(
    r'<section[^>]*id=["\']ingredients["\'][^>]*>(.*?)</section>', re.IGNORECASE | re.DOTALL
)


def _parse_fynd_app_data(html: str) -> dict[str, Any]:
    """Extract product fields from Tira/Fynd window.APP_DATA JSON blob."""
    marker = "window.APP_DATA = {"
    start = html.find(marker)
    if start < 0:
        return {}
    end = html.find("</script>", start)
    raw = html[start + len(marker) - 1 : end].strip().rstrip(";")
    try:
        app_data = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    pd = app_data.get("reduxData", {}).get("catalog", {}).get("product_details", {})
    if not pd:
        return {}

    attrs = pd.get("attributes", {}) if isinstance(pd.get("attributes"), dict) else {}

    # Images: medias list, type="image"
    images = [
        m["url"] for m in pd.get("medias", [])
        if isinstance(m, dict) and m.get("type") == "image" and m.get("url")
    ]

    # Category from categories list
    cats = pd.get("categories", [])
    category_hint = cats[0]["name"] if cats and isinstance(cats[0], dict) else None

    # Rating — 0 means no rating on Fynd
    rating_val = pd.get("rating")
    rating_cnt = pd.get("rating_count")
    rating_raw = f"{rating_val} ({rating_cnt})" if rating_val and rating_val > 0 else None

    price = attrs.get("min_price_effective")
    # price=0 means seller-based pricing — loaded via API post-render, not in HTML
    effective_price = float(price) if price else None
    is_available = attrs.get("is_available")

    return {
        "canonical_name": pd.get("name"),
        "brand_name": attrs.get("brand_name") or attrs.get("brand"),
        "current_price": effective_price,
        "current_price_raw": str(price) if effective_price else None,
        "stock_status_raw": "InStock" if is_available else ("OutOfStock" if is_available is False else None),
        "description_raw": pd.get("description"),
        "images": images,
        "category_hint": category_hint,
        "rating_raw": rating_raw,
    }


def parse_marketplace_html(
    *, html: str, retailer_slug: str, source_url: str, raw_capture_id: str
) -> ParsedSample:
    """Best-effort parse. Fields we cannot confidently extract go into missing_fields."""
    missing: set[str] = set()

    # Tira uses Fynd platform with window.APP_DATA — not JSON-LD
    if retailer_slug == "tira":
        fynd = _parse_fynd_app_data(html)
        missing_check = {
            "canonical_name": fynd.get("canonical_name"),
            "brand_name": fynd.get("brand_name"),
            "current_price": fynd.get("current_price"),
            "stock_status": fynd.get("stock_status_raw"),
            "images": fynd.get("images"),
        }
        for field, val in missing_check.items():
            if not val:
                missing.add(field)
        missing.add("ingredients")
        missing.add("offers")
        if not fynd.get("category_hint"):
            missing.add("category_hint")
        if not fynd.get("rating_raw"):
            missing.add("rating")
        return ParsedSample(
            retailer_slug=retailer_slug,
            source_url=source_url,
            raw_capture_id=raw_capture_id,
            canonical_name=fynd.get("canonical_name"),
            brand_name=fynd.get("brand_name"),
            current_price=fynd.get("current_price"),
            current_price_raw=fynd.get("current_price_raw"),
            stock_status_raw=fynd.get("stock_status_raw"),
            variants=[],
            ingredients_raw=None,
            ingredients_source=None,
            description_raw=fynd.get("description_raw"),
            images=fynd.get("images") or [],
            rating_raw=fynd.get("rating_raw"),
            offers_raw=[],
            missing_fields=missing,
        )

    products = _json_ld_products(html)
    product = products[0] if products else {}

    canonical_name = product.get("name") or None
    brand_name = (product.get("brand") or {}).get("name") if isinstance(product.get("brand"), dict) else None
    images = _extract_json_ld_images(product)
    # Purplle fallback: try __NEXT_DATA__ for full gallery if JSON-LD only has 1 image
    if retailer_slug == "purplle" and len(images) <= 1:
        next_images = _parse_purplle_next_data(html)
        if next_images:
            images = next_images

    offers_obj = product.get("offers")
    current_price: float | None = None
    current_price_raw: str | None = None
    stock_status_raw: str | None = None
    if isinstance(offers_obj, dict):
        raw_price = offers_obj.get("price")
        if raw_price is not None:
            current_price_raw = str(raw_price)
            try:
                current_price = float(raw_price)
            except (TypeError, ValueError):
                current_price = None
        availability = offers_obj.get("availability")
        if isinstance(availability, str):
            stock_status_raw = availability.rsplit("/", 1)[-1]

    rating_raw: str | None = None
    agg = product.get("aggregateRating")
    if isinstance(agg, dict):
        rv, rc = agg.get("ratingValue"), agg.get("reviewCount")
        if rv is not None and rc is not None:
            rating_raw = f"{rv} ({rc})"

    offers_raw = [
        re.sub(r"\s+", " ", m.group(1)).strip()
        for m in _OFFER_PATTERN.finditer(html)
    ]

    ingredients_match = _INGREDIENTS_PATTERN.search(html)
    ingredients_raw: str | None = None
    ingredients_source: Any = None
    if ingredients_match:
        ingredients_raw = re.sub(r"<[^>]+>", "", ingredients_match.group(1)).strip() or None
        ingredients_source = "text" if ingredients_raw else None

    if canonical_name is None: missing.add("canonical_name")
    if brand_name is None: missing.add("brand_name")
    if current_price is None: missing.add("current_price")
    if stock_status_raw is None: missing.add("stock_status")
    if ingredients_raw is None: missing.add("ingredients")
    if rating_raw is None: missing.add("rating")
    if not offers_raw: missing.add("offers")
    if not images: missing.add("images")
    missing.add("category_hint")  # marketplaces expose category via breadcrumb — deferred

    return ParsedSample(
        retailer_slug=retailer_slug,
        source_url=source_url,
        raw_capture_id=raw_capture_id,
        canonical_name=canonical_name,
        brand_name=brand_name,
        current_price=current_price,
        current_price_raw=current_price_raw,
        stock_status_raw=stock_status_raw,
        variants=[],
        ingredients_raw=ingredients_raw,
        ingredients_source=ingredients_source,
        description_raw=None,
        images=images,
        rating_raw=rating_raw,
        offers_raw=offers_raw,
        missing_fields=missing,
    )


class MarketplaceSampler:
    def __init__(self, retailer_slug: str, max_samples: int | None = None) -> None:
        self.retailer = retailer_by_slug(retailer_slug)
        self.max_samples = max_samples

    async def sample(
        self, n: int, raw_dir: Path, parsed_dir: Path
    ) -> list[ParsedSample]:
        urls = self.retailer.sample_product_urls
        if self.max_samples is not None:
            urls = urls[: self.max_samples]
        urls = urls[:n]

        proxy_config = None
        if self.retailer.needs_proxy:
            proxy_url = os.getenv("PROXY_URL")
            proxy_user = os.getenv("PROXY_USER")
            proxy_pass = os.getenv("PROXY_PASS")
            if proxy_url and proxy_user and proxy_pass:
                proxy_config = {
                    "server": proxy_url,
                    "username": proxy_user,
                    "password": proxy_pass,
                }

        headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"

        via = "smartproxy" if proxy_config else "direct"
        log.info("marketplace_fetch_start", retailer=self.retailer.slug, urls=len(urls), via=via)

        samples: list[ParsedSample] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless, proxy=proxy_config)
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
            )
            for url in urls:
                status = 0
                body = ""
                for attempt in range(3):
                    page = await context.new_page()
                    await Stealth().use_async(page)
                    try:
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        status = resp.status if resp else 0
                        await page.wait_for_timeout(2500)
                        body = await page.content()
                        await page.close()
                        break
                    except Exception as e:  # noqa: BLE001
                        await page.close()
                        if attempt == 2:
                            log.warning("marketplace_fetch_failed", retailer=self.retailer.slug,
                                        url=url, attempts=3, error=str(e))
                        else:
                            wait_s = 3 * (attempt + 1)
                            log.info("marketplace_fetch_retry", retailer=self.retailer.slug,
                                     url=url, attempt=attempt + 1, wait_s=wait_s)
                            await asyncio.sleep(wait_s)

                rc = RawCapture(
                    retailer_slug=self.retailer.slug,
                    source_url=url,
                    tier_used="marketplace-selector",
                    fetched_at=datetime.now(timezone.utc),
                    fetcher_version=_FETCHER_VERSION,
                    content_type="text/html",
                    body=body,
                    http_status=status,
                )
                cid = persist_raw(rc, raw_dir)

                ps = parse_marketplace_html(
                    html=body, retailer_slug=self.retailer.slug,
                    source_url=url, raw_capture_id=cid,
                )
                persist_parsed(ps, parsed_dir)
                samples.append(ps)

            await browser.close()
        return samples
