"""Fetch product pages via httpx (no JS execution).

Used for custom D2C brands whose product data is server-rendered (JSON-LD,
OG tags, __NEXT_DATA__).  Much faster than Playwright and avoids bot-
detection heuristics that trigger JS-only shells.
"""
from __future__ import annotations

import asyncio

import httpx
import structlog

log = structlog.get_logger()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    # No Accept-Encoding — let httpx negotiate automatically to avoid brotli issues
}
_TIMEOUT = 30
_CONCURRENCY = 8
_MAX_RETRIES = 2


async def _fetch_one(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    for attempt in range(_MAX_RETRIES):
        try:
            r = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
            return r.text, r.status_code
        except Exception as exc:
            if attempt == _MAX_RETRIES - 1:
                log.warning("direct_fetch_failed", url=url, error=str(exc))
                return "", 0
            await asyncio.sleep(2 * (attempt + 1))
    return "", 0


async def fetch_pages_direct(
    urls: list[str],
) -> list[tuple[str, str, int]]:
    """Fetch a list of URLs with httpx. Returns list of (url, html, http_status)."""
    log.info("direct_fetch_start", urls=len(urls))
    results: list[tuple[str, str, int]] = []
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def bounded(url: str) -> tuple[str, str, int]:
        async with sem:
            html, status = await _fetch_one(client, url)
            return url, html, status

    async with httpx.AsyncClient() as client:
        tasks = [bounded(u) for u in urls]
        results = list(await asyncio.gather(*tasks))

    ok = sum(1 for _, html, _ in results if html)
    log.info("direct_fetch_done", total=len(urls), ok=ok)
    return results
