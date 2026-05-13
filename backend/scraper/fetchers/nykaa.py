"""Fetch Nykaa product and search pages.

Two proxy tiers:
  - URL discovery (search/category pages): ScraperAPI standard (1 credit each)
    Nykaa's Akamai CDN blocks residential IPs on listing pages consistently.
  - Product pages: Smartproxy residential (bandwidth-based, effectively free)
    Individual product pages work fine with residential proxy.
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import quote

import httpx
import structlog

log = structlog.get_logger()

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_BASE = "https://www.nykaa.com"
_SKIN_CAT = "8377"   # Nykaa skin/beauty top-level category
_DELAY = 1.0         # seconds between requests


def _smartproxy_client(proxy_url: str, proxy_user: str, proxy_pass: str) -> httpx.AsyncClient:
    proxy = f"http://{proxy_user}:{proxy_pass}@{proxy_url.removeprefix('http://')}"
    return httpx.AsyncClient(proxy=proxy, timeout=30.0, verify=False,
                              follow_redirects=True, headers={"User-Agent": _UA})


def _scraperapi_client(scraperapi_key: str) -> httpx.AsyncClient:
    proxy = f"http://scraperapi:{scraperapi_key}@proxy-server.scraperapi.com:8001"
    return httpx.AsyncClient(proxy=proxy, timeout=30.0, verify=False,
                              follow_redirects=True, headers={"User-Agent": _UA})


async def fetch_nykaa_page(url: str, proxy_url: str, proxy_user: str, proxy_pass: str) -> str | None:
    """Fetch a single Nykaa product page via Smartproxy with retries. Returns HTML or None."""
    delays = [2.0, 4.0, 8.0]
    for attempt, backoff in enumerate([0.0] + delays):
        if backoff:
            await asyncio.sleep(backoff)
        async with _smartproxy_client(proxy_url, proxy_user, proxy_pass) as c:
            try:
                r = await c.get(url)
                if r.status_code == 200:
                    return r.text
                if r.status_code != 403 or attempt == len(delays):
                    log.warning("nykaa_fetch_failed", url=url, status=r.status_code, attempt=attempt + 1)
                    return None
                log.info("nykaa_fetch_retry", url=url, attempt=attempt + 1, backoff=backoff)
            except Exception as exc:
                if attempt == len(delays):
                    log.error("nykaa_fetch_error", url=url, error=str(exc))
                    return None
                log.info("nykaa_fetch_retry", url=url, attempt=attempt + 1, error=str(exc))
    return None


async def fetch_nykaa_page_scraperapi(url: str, scraperapi_key: str) -> str | None:
    """Fetch a single Nykaa product page via ScraperAPI standard (1 credit). Returns HTML or None."""
    async with _scraperapi_client(scraperapi_key) as c:
        try:
            r = await c.get(url)
            if r.status_code == 200:
                return r.text
            log.warning("nykaa_scraperapi_fetch_failed", url=url, status=r.status_code)
            return None
        except Exception as exc:
            log.error("nykaa_scraperapi_fetch_error", url=url, error=str(exc))
            return None


async def fetch_nykaa_brand_product_urls(
    brand_search_name: str,
    scraperapi_key: str,
    limit: int = 500,
) -> list[dict]:
    """Discover Nykaa product URLs for a brand via paginated search (ScraperAPI standard).

    Uses Nykaa's search endpoint filtered to skin category (8377) so only
    skincare products are returned. Costs 1 ScraperAPI credit per page.

    Returns list of dicts with keys: url, name, price, mrp, brand.
    """
    results: list[dict] = []
    seen_urls: set[str] = set()
    page = 1

    async with _scraperapi_client(scraperapi_key) as c:
        while len(results) < limit:
            url = (
                f"{_BASE}/search/result/?q={quote(brand_search_name)}"
                f"&ptype=product&sort=relevance&category={_SKIN_CAT}&page_no={page}"
            )
            log.info("nykaa_brand_discovery", brand=brand_search_name, page=page)
            try:
                r = await c.get(url)
            except Exception as exc:
                log.error("nykaa_search_error", brand=brand_search_name, error=str(exc))
                break

            if r.status_code != 200:
                log.warning("nykaa_discovery_failed", brand=brand_search_name,
                            status=r.status_code)
                break

            page_products = _parse_category_product_urls(r.text, brand_search_name)
            if not page_products:
                break

            new_on_page = [p for p in page_products if p["url"] not in seen_urls]
            seen_urls.update(p["url"] for p in page_products)
            results.extend(new_on_page)
            log.info("nykaa_brand_page_done", brand=brand_search_name, page=page,
                     found=len(page_products), new=len(new_on_page), total=len(results))

            # Stop if no new unique URLs (Nykaa is recycling results)
            if not new_on_page:
                log.info("nykaa_brand_no_new_urls", brand=brand_search_name, page=page)
                break
            if len(page_products) < 20:
                break  # last page (Nykaa returns 20 per page)
            page += 1
            await asyncio.sleep(_DELAY)

    return results[:limit]


def _parse_category_product_urls(html: str, brand_filter: str) -> list[dict]:
    """Extract product URLs from a Nykaa search results or category page."""
    state = _extract_preloaded_state(html)
    if not state:
        return []

    # Nykaa stores product list at categoryListing.listingData.products
    cl = state.get("categoryListing") or {}
    ld = cl.get("listingData") or {}
    products_raw = ld.get("products") or []

    # Fallback: some pages use searchListingPage.listingData.products
    if not products_raw:
        slp = state.get("searchListingPage") or {}
        sld = slp.get("listingData") or {}
        products_raw = sld.get("products") or slp.get("products") or []

    brand_lower = brand_filter.lower()
    results = []

    for p in products_raw:
        if not isinstance(p, dict):
            continue
        # Filter by brand — search already filtered but verify to avoid cross-brand hits
        p_brand = (p.get("brandName") or p.get("brand") or "").lower()
        if p_brand and brand_lower not in p_brand and p_brand not in brand_lower:
            continue
        slug = p.get("slug") or p.get("productUrl") or p.get("url") or ""
        if not slug:
            continue
        url = slug if slug.startswith("http") else f"{_BASE}/{slug.lstrip('/')}"
        results.append({
            "url": url,
            "name": p.get("name") or p.get("title") or "",
            "price": p.get("price") or p.get("offerPrice"),
            "mrp": p.get("mrp"),
            "brand": p.get("brandName") or p.get("brand") or brand_filter,
        })

    return results


def _extract_preloaded_state(html: str) -> dict:
    """Extract and parse window.__PRELOADED_STATE__ from Nykaa HTML."""
    idx = html.find("window.__PRELOADED_STATE__")
    if idx < 0:
        return {}
    try:
        start = html.index("{", idx)
        end = html.find("</script>", start)
        raw = html[start:end].rstrip("; \n")
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {}
