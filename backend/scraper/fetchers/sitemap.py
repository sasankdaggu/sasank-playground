"""Fetch product URLs from brand sitemaps (sitemap index or direct sitemap)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
import structlog

log = structlog.get_logger()

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
_TIMEOUT = 30


async def _fetch_locs(url: str, scraperapi_key: str = "") -> list[str]:
    """Fetch a single sitemap XML and return all <loc> values."""
    fetch_url = (
        f"http://api.scraperapi.com?api_key={scraperapi_key}&url={url}"
        if scraperapi_key else url
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
            r = await c.get(fetch_url, headers=_HEADERS)
            if r.status_code != 200:
                log.warning("sitemap_fetch_failed", url=url, status=r.status_code)
                return []
            if "<loc>" not in r.text:
                log.warning("sitemap_not_xml", url=url, content_type=r.headers.get("content-type"))
                return []
            return re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, re.DOTALL)
    except Exception as exc:
        log.warning("sitemap_fetch_error", url=url, error=str(exc))
        return []


async def fetch_product_urls(
    sitemap_url: str,
    product_url_pattern: str,
    exclude_patterns: tuple[str, ...] = (),
    limit: int = 0,
    scraperapi_key: str = "",
    min_path_depth: int = 0,
) -> list[str]:
    """
    Fetch all product URLs from a sitemap or sitemap index.

    Args:
        sitemap_url: URL of the sitemap or sitemap index XML.
        product_url_pattern: Substring that must appear in a URL for it to be a product page.
        exclude_patterns: Substrings that disqualify a URL (e.g. '/reviews', '/questions').
        limit: Max URLs to return (0 = no limit).
    """
    locs = await _fetch_locs(sitemap_url, scraperapi_key)
    if not locs:
        return []

    # Detect sitemap index: all locs are themselves .xml sitemaps
    sub_sitemaps = [l for l in locs if re.search(r"sitemap.*\.xml", l, re.IGNORECASE)]
    if sub_sitemaps:
        # It's an index — collect product URLs from relevant sub-sitemaps only
        # (skip blog/posts/reviews sub-sitemaps)
        product_sub = [
            s for s in sub_sitemaps
            if not any(x in s.lower() for x in ("blog", "post", "review", "question", "article"))
        ]
        log.info("sitemap_index", total_subs=len(sub_sitemaps), product_subs=len(product_sub), url=sitemap_url)
        all_locs: list[str] = []
        for sub in product_sub:
            all_locs.extend(await _fetch_locs(sub, scraperapi_key))
        locs = all_locs

    # Filter to product URLs
    results: list[str] = []
    for loc in locs:
        if product_url_pattern not in loc:
            continue
        if any(ex in loc for ex in exclude_patterns):
            continue
        if min_path_depth:
            segments = [s for s in urlparse(loc).path.split("/") if s]
            if len(segments) < min_path_depth:
                continue
        results.append(loc)

    if limit:
        results = results[:limit]

    log.info("sitemap_product_urls", sitemap=sitemap_url, found=len(results))
    return results
