"""Sitemap-based product URL discovery — static XML, no JS rendering required.

All three marketplaces expose their product catalogs via sitemaps. This is
far more reliable than scraping category pages (which are React/XHR-heavy).

Discovery flow:
  1. Fetch the sitemap index for each retailer
  2. Identify product sub-sitemaps (via regex pattern)
  3. Fetch each sub-sitemap and extract <loc> URLs
  4. Apply keyword filter to narrow to face skincare (Nykaa/Tira)
  5. Purplle: use per-category sitemaps (already face-specific)
"""
from __future__ import annotations

import asyncio
import re
import urllib.parse
from dataclasses import dataclass, field

import httpx
import structlog

log = structlog.get_logger()

_FACE_SKINCARE_KEYWORDS = (
    "face", "moisturis", "moisturiz", "cleanser", "toner", "serum",
    "sunscreen", "spf-", "retinol", "niacinamide", "hyaluron", "exfoliat",
    "eye-cream", "eye-serum", "under-eye", "pore", "acne-spot", "acne-scar",
    "brightening", "skin-care",
)


@dataclass(frozen=True)
class SitemapSource:
    retailer_slug: str
    # Either an index URL + pattern to identify product sub-sitemaps…
    index_url: str = ""
    product_sitemap_re: str = ""          # regex applied to each <loc> in the index
    # …or a direct list of category sitemap URLs (for Purplle)
    direct_sitemap_urls: tuple[str, ...] = field(default_factory=tuple)
    # Keyword filter on product URL slug (empty → accept all)
    face_keywords: tuple[str, ...] = field(default_factory=tuple)
    # Keywords that veto a URL even when a positive keyword matches
    exclude_keywords: tuple[str, ...] = field(default_factory=tuple)


FACE_SKINCARE_SOURCES: tuple[SitemapSource, ...] = (
    # ── Nykaa: 7 product sitemaps, ~50k URLs each ──────────────────────────
    SitemapSource(
        retailer_slug="nykaa",
        index_url="https://www.nykaa.com/sitemap-v2/sitemap-products-index.xml",
        product_sitemap_re=r"sitemap-products-\d+\.xml$",
        face_keywords=_FACE_SKINCARE_KEYWORDS,
        exclude_keywords=("shampoo", "conditioner", "mascara", "lipstick", "nail-",
                          "body-wash", "body-lotion", "hair-oil", "hair-mask",
                          "foundation", "blush", "eyeshadow", "kajal", "kohl",
                          "pendant", "mangalsutra", "jewellery", "jewelry",
                          "perfume", "fragrance", "bath-"),
    ),
    # ── Tira: 104 product sub-sitemaps, ~500 URLs each ─────────────────────
    SitemapSource(
        retailer_slug="tira",
        index_url="https://www.tirabeauty.com/sitemap.xml",
        product_sitemap_re=r"products/\d+/page\.sitemap\.xml$",
        face_keywords=_FACE_SKINCARE_KEYWORDS,
        exclude_keywords=("shampoo", "conditioner", "mascara", "lipstick", "nail-",
                          "body-wash", "body-lotion", "hair-oil", "hair-mask",
                          "perfume", "fragrance"),
    ),
    # ── Purplle: per-category sitemaps (already face-specific) ─────────────
    # Purplle's all-subcategories.xml is a sitemap index; we filter by category name.
    SitemapSource(
        retailer_slug="purplle",
        index_url="https://www.purplle.com/sitemap/products/all-subcategories.xml",
        # Accept any skincare sub-sitemap except body sunscreen and lip care
        product_sitemap_re=r"category-skin(?:care|-.+?)-(?!sun-care-body|lip-care)",
        face_keywords=(),   # category sitemaps already scoped to face skincare
        exclude_keywords=(),
    ),
)


def _is_face_skincare(url: str, source: SitemapSource) -> bool:
    if not source.face_keywords:
        return True
    slug = url.split("/")[-1].lower()
    path = url.lower()
    for kw in source.exclude_keywords:
        if kw in path:
            return False
    return any(kw in path for kw in source.face_keywords)


async def _fetch_xml(scraperapi_key: str, url: str) -> str:
    """Fetch a URL via ScraperAPI (no JS render — sitemaps are static XML)."""
    api_url = (
        f"http://api.scraperapi.com"
        f"?api_key={scraperapi_key}"
        f"&url={urllib.parse.quote(url, safe='')}"
        f"&country_code=in"
    )
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(api_url)
            if resp.status_code == 429:
                await asyncio.sleep(10 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                log.warning("sitemap_fetch_error", url=url, status=resp.status_code)
                return ""
            return resp.text
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt == 2:
                log.warning("sitemap_fetch_failed", url=url, error=str(exc))
                return ""
            await asyncio.sleep(5 * (attempt + 1))
    return ""


def _extract_locs(xml: str) -> list[str]:
    return re.findall(r"<loc>\s*(https://[^\s<]+)\s*</loc>", xml)


async def discover_from_sitemaps(
    source: SitemapSource,
    scraperapi_key: str,
    max_sitemaps: int = 0,           # 0 = no limit
    category_hint: str = "face_skincare",
) -> list[tuple[str, str]]:          # [(url, category_hint)]
    """Discover face skincare product URLs from a retailer's sitemaps.

    Returns list of (product_url, category_hint) tuples.
    """
    # Step 1: fetch index → collect product sub-sitemaps
    log.info("sitemap_index_fetch", retailer=source.retailer_slug, url=source.index_url)
    index_xml = await _fetch_xml(scraperapi_key, source.index_url)
    if not index_xml:
        return []

    all_sub = _extract_locs(index_xml)
    pattern = re.compile(source.product_sitemap_re, re.IGNORECASE) if source.product_sitemap_re else None
    sub_sitemaps = [u for u in all_sub if pattern is None or pattern.search(u)]
    if max_sitemaps:
        sub_sitemaps = sub_sitemaps[:max_sitemaps]

    log.info("sitemap_sub_count",
             retailer=source.retailer_slug, total=len(all_sub), filtered=len(sub_sitemaps))

    # Step 2: fetch each sub-sitemap and extract + filter product URLs
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for i, sub_url in enumerate(sub_sitemaps):
        xml = await _fetch_xml(scraperapi_key, sub_url)
        if not xml:
            continue
        product_urls = _extract_locs(xml)
        for url in product_urls:
            if url in seen:
                continue
            if _is_face_skincare(url, source):
                seen.add(url)
                # Derive category hint from URL or sitemap filename
                hint = _infer_hint(url, sub_url)
                results.append((url, hint))

        if i % 10 == 0:
            log.info("sitemap_progress",
                     retailer=source.retailer_slug, sitemap=i + 1,
                     of=len(sub_sitemaps), face_skincare_so_far=len(results))
        await asyncio.sleep(0.3)  # gentle pacing

    log.info("sitemap_discovery_done",
             retailer=source.retailer_slug, total=len(results))
    return results


def _infer_hint(product_url: str, sitemap_url: str) -> str:
    """Derive category_hint from sitemap filename or product URL slug."""
    # Purplle: category-skincare-face-wash.xml → face_wash
    m = re.search(r"category-skin(?:care|[^.]+)-(.+)\.xml", sitemap_url)
    if m:
        return m.group(1).replace("-", "_")
    # Nykaa/Tira: infer from product URL keywords
    slug = product_url.lower()
    for kw, hint in [
        ("face-wash", "face_wash"), ("cleanser", "face_wash"),
        ("serum", "serum"), ("toner", "toner"),
        ("moisturis", "moisturizer"), ("moisturiz", "moisturizer"),
        ("sunscreen", "sunscreen"), ("spf", "sunscreen"),
        ("eye-cream", "eye_care"), ("eye-serum", "eye_care"), ("under-eye", "eye_care"),
        ("face-mask", "face_mask"), ("face-pack", "face_mask"),
        ("retinol", "serum"), ("niacinamide", "serum"),
    ]:
        if kw in slug:
            return hint
    return "face_skincare"
