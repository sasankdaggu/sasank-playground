from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from spike.config import retailer_by_slug
from spike.models import ParsedSample, RawCapture, Variant
from spike.samplers.base import persist_parsed, persist_raw

log = structlog.get_logger()
_FETCHER_VERSION = "spike-shopify-0.0.2"


def _scraperapi_proxy() -> str | None:
    key = os.getenv("SCRAPERAPI_KEY")
    if not key:
        return None
    return f"http://scraperapi:{key}@proxy-server.scraperapi.com:8001"


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
async def _fetch_url(url: str) -> httpx.Response:
    proxy = _scraperapi_proxy()
    kwargs: dict = {"timeout": 60.0}
    if proxy:
        kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**kwargs) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp


class ShopifySampler:
    """Tier 0: reads Shopify's open /products.json endpoint."""

    def __init__(self, retailer_slug: str) -> None:
        self.retailer = retailer_by_slug(retailer_slug)
        if self.retailer.products_json_url is None:
            raise ValueError(f"{retailer_slug} is not a Shopify retailer")

    async def sample(
        self, n: int, raw_dir: Path, parsed_dir: Path
    ) -> list[ParsedSample]:
        via = "scraperapi" if _scraperapi_proxy() else "direct"
        log.info("shopify_fetch", retailer=self.retailer.slug, via=via)
        resp = await _fetch_url(self.retailer.products_json_url)

        rc = RawCapture(
            retailer_slug=self.retailer.slug,
            source_url=self.retailer.products_json_url or "",
            tier_used="shopify",
            fetched_at=datetime.now(timezone.utc),
            fetcher_version=_FETCHER_VERSION,
            content_type=resp.headers.get("content-type", "application/json"),
            body=resp.text,
            http_status=resp.status_code,
        )
        cid = persist_raw(rc, raw_dir)

        payload = json.loads(resp.text)
        products = payload.get("products", [])[:n]

        samples: list[ParsedSample] = []
        for p in products:
            ps = self._parse_product(p, cid)
            persist_parsed(ps, parsed_dir)
            samples.append(ps)
        return samples

    def _parse_product(self, p: dict[str, Any], raw_capture_id: str) -> ParsedSample:
        missing: set[str] = set()

        canonical_name = p.get("title") or None
        if not canonical_name:
            missing.add("canonical_name")

        brand_name = p.get("vendor") or None

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
            Variant(
                option_name=None if v.get("title") in (None, "Default Title") else "Size/Option",
                option_value=None if v.get("title") == "Default Title" else v.get("title"),
                sku=v.get("sku") or None,
                price=float(v["price"]) if v.get("price") else None,
                compare_at_price=float(v["compare_at_price"]) if v.get("compare_at_price") else None,
                available=v.get("available"),
            )
            for v in variants_raw
        ]

        first = variants[0] if variants else None
        current_price = first.price if first else None
        current_price_raw = variants_raw[0].get("price") if variants_raw else None
        compare_at_price = first.compare_at_price if first else None
        if current_price is None:
            missing.add("current_price")

        # Shopify /products.json never exposes ingredients structurally.
        missing.add("ingredients")
        stock_status_raw = (
            "in_stock" if any(v.get("available") for v in variants_raw) else "out_of_stock"
        )
        # Rating is never in /products.json.
        missing.add("rating")

        return ParsedSample(
            retailer_slug=self.retailer.slug,
            source_url=f"{self.retailer.base_url}/products/{p.get('handle', '')}",
            raw_capture_id=raw_capture_id,
            canonical_name=canonical_name,
            brand_name=brand_name,
            category_hint=category_hint,
            current_price=current_price,
            current_price_raw=str(current_price_raw) if current_price_raw else None,
            compare_at_price=compare_at_price,
            stock_status_raw=stock_status_raw,
            variants=variants,
            description_raw=description_raw,
            images=images,
            missing_fields=missing,
        )
