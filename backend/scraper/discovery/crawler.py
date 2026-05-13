"""Paginated category-page crawler — extracts product URLs from marketplace listing pages.

Primary path: ScraperAPI render API (httpx) — handles JS rendering + geo-access in one call.
Fallback path: Playwright + proxy — for environments where ScraperAPI is not configured.
"""
from __future__ import annotations

import asyncio
import re
import urllib.parse
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import structlog

from scraper.discovery.categories import DiscoveryCategory

log = structlog.get_logger()

# Per-retailer patterns for extracting product page hrefs from rendered category HTML.
# Nykaa:   /some-product-name/p/12345678
# Tira:    /products/brand-product-slug  (Fynd, ends with slug not numeric ID)
# Purplle: /product/brand-name-variant-12345  (ends with numeric ID)
_PRODUCT_HREF_PATTERNS: dict[str, re.Pattern[str]] = {
    "nykaa":   re.compile(r'href=["\'](/[^\s"\'<>]+/p/\d+[^\s"\'<>?#]*)["\']'),
    "tira":    re.compile(r'href=["\'](/products/[a-z0-9][a-z0-9-]{3,}[^\s"\'<>?#]*)["\']'),
    "purplle": re.compile(r'href=["\'](/product/[a-z0-9][a-z0-9-]+-\d+[^\s"\'<>?#]*)["\']'),
}


def _paginate(base_url: str, param: str, page: int) -> str:
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params[param] = [str(page)]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


def _extract_urls(html: str, retailer_slug: str, base_url: str) -> list[str]:
    pattern = _PRODUCT_HREF_PATTERNS.get(retailer_slug)
    if not pattern:
        return []
    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    seen: dict[str, None] = {}
    for m in pattern.finditer(html):
        path = m.group(1).split("?")[0].split("#")[0]
        seen[domain + path] = None
    return list(seen)


async def discover_category_urls(
    category: DiscoveryCategory,
    *,
    scraperapi_key: str = "",
    proxy_url: str = "",
    proxy_user: str = "",
    proxy_pass: str = "",
    headless: bool = True,
) -> list[str]:
    """Crawl all pages of a category listing; return deduplicated product URLs.

    Uses ScraperAPI render API when scraperapi_key is set (recommended — handles JS + geo).
    Falls back to Playwright + proxy otherwise.
    """
    if scraperapi_key:
        return await _discover_scraperapi(category, scraperapi_key)
    return await _discover_playwright(category, proxy_url, proxy_user, proxy_pass, headless)


# ── ScraperAPI path ────────────────────────────────────────────────────────────

async def _scrape_url(scraperapi_key: str, url: str) -> tuple[str, int]:
    """Fetch a URL via ScraperAPI render API — returns (html, http_status)."""
    api_url = (
        "http://api.scraperapi.com"
        f"?api_key={scraperapi_key}"
        f"&url={urllib.parse.quote(url, safe='')}"
        "&render=true"       # JS rendering
        "&country_code=in"   # India IP for geo-access
    )
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.get(api_url)
            if resp.status_code == 429:
                wait_s = 10 * (attempt + 1)
                log.info("scraperapi_rate_limited", url=url, attempt=attempt, wait_s=wait_s)
                await asyncio.sleep(wait_s)
                continue
            return resp.text, resp.status_code
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt == 2:
                log.warning("scraperapi_fetch_failed", url=url, error=str(exc))
                return "", 0
            await asyncio.sleep(5 * (attempt + 1))
    return "", 0


async def _discover_scraperapi(category: DiscoveryCategory, scraperapi_key: str) -> list[str]:
    all_urls: list[str] = []
    seen: set[str] = set()

    for page_num in range(1, category.max_pages + 1):
        url = _paginate(category.url, category.pagination_param, page_num)
        html, status = await _scrape_url(scraperapi_key, url)

        if not html or status >= 400:
            log.warning("discovery_page_failed",
                        retailer=category.retailer_slug, category=category.hint,
                        page=page_num, status=status)
            break

        page_urls = _extract_urls(html, category.retailer_slug, category.url)
        new_urls = [u for u in page_urls if u not in seen]

        if not new_urls:
            log.info("discovery_exhausted",
                     retailer=category.retailer_slug, category=category.hint,
                     page=page_num, total=len(all_urls))
            break

        seen.update(new_urls)
        all_urls.extend(new_urls)
        log.info("discovery_page",
                 retailer=category.retailer_slug, category=category.hint,
                 page=page_num, new=len(new_urls), cumulative=len(all_urls))

        await asyncio.sleep(1)  # be polite between pages

    return all_urls


# ── Playwright fallback path ───────────────────────────────────────────────────

async def _discover_playwright(
    category: DiscoveryCategory,
    proxy_url: str,
    proxy_user: str,
    proxy_pass: str,
    headless: bool,
) -> list[str]:
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    _USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    proxy_config = None
    if proxy_url and proxy_user and proxy_pass:
        proxy_config = {"server": proxy_url, "username": proxy_user, "password": proxy_pass}

    all_urls: list[str] = []
    seen: set[str] = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, proxy=proxy_config)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=_USER_AGENT,
            locale="en-IN",
        )

        for page_num in range(1, category.max_pages + 1):
            url = _paginate(category.url, category.pagination_param, page_num)
            html, status = await _fetch_playwright(context, url)

            if not html or status >= 400:
                log.warning("discovery_page_failed",
                            retailer=category.retailer_slug, category=category.hint,
                            page=page_num, status=status)
                break

            page_urls = _extract_urls(html, category.retailer_slug, category.url)
            new_urls = [u for u in page_urls if u not in seen]

            if not new_urls:
                log.info("discovery_exhausted",
                         retailer=category.retailer_slug, category=category.hint,
                         page=page_num, total=len(all_urls))
                break

            seen.update(new_urls)
            all_urls.extend(new_urls)
            log.info("discovery_page",
                     retailer=category.retailer_slug, category=category.hint,
                     page=page_num, new=len(new_urls), cumulative=len(all_urls))

        await browser.close()

    return all_urls


async def _fetch_playwright(context, url: str) -> tuple[str, int]:
    from playwright_stealth import Stealth
    for attempt in range(3):
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            status = resp.status if resp else 0
            await page.wait_for_timeout(3_000)
            html = await page.content()
            await page.close()
            return html, status
        except Exception as exc:
            await page.close()
            if attempt == 2:
                log.warning("discovery_playwright_failed", url=url, error=str(exc))
                return "", 0
            await asyncio.sleep(3 * (attempt + 1))
    return "", 0
