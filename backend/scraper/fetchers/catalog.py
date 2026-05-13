"""Crawl paginated category pages via Playwright to collect product URLs.

Used for brands like Forest Essentials (Magento 2) where product URLs are
not in the sitemap — only category listing pages are known, and the product
grid is JS-rendered.
"""
from __future__ import annotations

import asyncio
import re

import httpx
import structlog
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

log = structlog.get_logger()

_HTTPX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_PRODUCT_LINK_SELECTOR = ".product-item-link"
_MAX_PAGES = 50


async def _crawl_category(context, base_url: str) -> set[str]:
    """Crawl all paginated pages of a single category URL, returning product hrefs."""
    product_urls: set[str] = set()
    for page_num in range(1, _MAX_PAGES + 1):
        url = base_url if page_num == 1 else f"{base_url}?p={page_num}"
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            await page.wait_for_timeout(2_000)
            links = await page.query_selector_all(_PRODUCT_LINK_SELECTOR)
            hrefs = set()
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    hrefs.add(href)
            await page.close()

            if not hrefs:
                break
            new = hrefs - product_urls
            product_urls |= hrefs
            log.info("catalog_page_crawled", url=url, page=page_num,
                     found=len(hrefs), new=len(new), total=len(product_urls))
            if not new:
                break
        except Exception as exc:
            await page.close()
            log.warning("catalog_page_error", url=url, page=page_num, error=str(exc))
            break

    return product_urls


async def fetch_product_urls_from_catalog(
    catalog_page_urls: list[str],
    headless: bool = True,
    limit: int = 0,
) -> list[str]:
    """Crawl multiple category pages via Playwright, returning deduplicated product URLs."""
    all_urls: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=_USER_AGENT,
            locale="en-IN",
        )
        for cat_url in catalog_page_urls:
            urls = await _crawl_category(context, cat_url)
            all_urls |= urls

        await browser.close()

    result = list(all_urls)
    if limit:
        result = result[:limit]
    log.info("catalog_crawl_done", category_pages=len(catalog_page_urls),
             total_product_urls=len(result))
    return result


async def fetch_product_urls_via_httpx(
    catalog_page_urls: list[str],
    link_regex: str,
    base_url: str,
    limit: int = 0,
) -> list[str]:
    """Fetch category pages via httpx and extract product URLs using a regex.

    The regex must have one capture group returning a URL path (starting with /)
    or a full URL.  Relative paths are prepended with base_url.
    """
    pattern = re.compile(link_regex)
    all_paths: set[str] = set()

    async with httpx.AsyncClient() as client:
        for url in catalog_page_urls:
            try:
                r = await client.get(
                    url, headers=_HTTPX_HEADERS, timeout=30, follow_redirects=True,
                )
                html = r.text
            except Exception as exc:
                log.warning("catalog_httpx_error", url=url, error=str(exc))
                continue
            found = {m.group(1) for m in pattern.finditer(html)}
            all_paths |= found
            log.info("catalog_httpx_page", url=url, found=len(found), total=len(all_paths))

    result = [
        f"{base_url}{p}" if p.startswith("/") else p
        for p in all_paths
    ]
    if limit:
        result = result[:limit]
    log.info("catalog_httpx_done", category_pages=len(catalog_page_urls),
             total_product_urls=len(result))
    return result
