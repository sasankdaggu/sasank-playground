"""Fetch marketplace product pages via Playwright — optionally via Smartproxy."""
from __future__ import annotations

import asyncio

import structlog
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

log = structlog.get_logger()

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_MAX_RETRIES = 3


async def fetch_marketplace_pages(
    urls: list[str],
    *,
    proxy_url: str = "",
    proxy_user: str = "",
    proxy_pass: str = "",
    headless: bool = True,
) -> list[tuple[str, str, int]]:
    """Fetch a list of URLs. Returns list of (url, html, http_status)."""
    proxy_config = None
    if proxy_url and proxy_user and proxy_pass:
        proxy_config = {"server": proxy_url, "username": proxy_user, "password": proxy_pass}

    via = "smartproxy" if proxy_config else "direct"
    log.info("marketplace_fetch_start", urls=len(urls), via=via)

    results: list[tuple[str, str, int]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=proxy_config)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=_USER_AGENT,
            locale="en-IN",
        )

        for url in urls:
            html, status = await _fetch_with_retry(context, url)
            results.append((url, html, status))

        await browser.close()

    return results


async def _fetch_with_retry(context, url: str) -> tuple[str, int]:
    for attempt in range(_MAX_RETRIES):
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            status = resp.status if resp else 0
            await page.wait_for_timeout(2_500)
            html = await page.content()
            await page.close()
            return html, status
        except Exception as exc:
            await page.close()
            if attempt == _MAX_RETRIES - 1:
                log.warning("marketplace_fetch_failed", url=url, attempts=_MAX_RETRIES, error=str(exc))
                return "", 0
            wait = 3 * (attempt + 1)
            log.info("marketplace_fetch_retry", url=url, attempt=attempt + 1, wait_s=wait)
            await asyncio.sleep(wait)

    return "", 0
