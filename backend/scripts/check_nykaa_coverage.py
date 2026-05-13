"""
Check how many of our catalog brands/products are available on Nykaa.

Queries Nykaa's search API for each of our 65 D2C brands and reports:
  - How many products each brand has on Nykaa (skincare only)
  - Our current DB count for the same brand
  - Coverage gap

Cost: tries direct fetch first (0 credits); falls back to standard ScraperAPI
      (1 credit/request). Residential proxy is NOT used. ~65 total requests.

Usage:
    python -m scripts.check_nykaa_coverage
    python -m scripts.check_nykaa_coverage --no-proxy   # direct only, no ScraperAPI
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx
import psycopg
import structlog
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
log = structlog.get_logger()

# ── Brand name overrides ──────────────────────────────────────────────────────
# Maps retailer slug → search term to use on Nykaa (when our DB name differs)
NYKAA_SEARCH_NAME: dict[str, str] = {
    "82e":              "82°E",
    "mcaffeine":        "MCaffeine",
    "dot_and_key":      "Dot & Key",
    "dr_sheths":        "Dr. Sheth's",
    "innisfree_in":     "Innisfree",
    "kiehls_in":        "Kiehl's",
    "dermalogica_in":   "Dermalogica",
    "pixi_in":          "Pixi",
    "thebodyshop_in":   "The Body Shop",
    "simple_in":        "Simple",
    "cerave_in":        "CeraVe",
    "cetaphil_in":      "Cetaphil",
    "neutrogena_in":    "Neutrogena",
    "olay_in":          "Olay",
    "bioderma_in":      "Bioderma",
    "paulas_choice_in": "Paula's Choice",
    "ponds_in":         "Pond's",
    "the_face_shop_in": "The Face Shop",
    "world_of_asaya":   "Asaya",
    "lets_hyphen":      "Let's Hyphen",
    "the_deconstruct":  "The Deconstruct",
    "the_derma_co":     "The Derma Co",
    "the_pink_foundry": "The Pink Foundry",
    "forest_essentials":"Forest Essentials",
    "kama_ayurveda":    "Kama Ayurveda",
    "bare_necessities": "Bare Necessities",
    "conscious_chemist":"Conscious Chemist",
    "daughter_earth":   "Daughter Earth",
    "beauty_of_joseon": "Beauty of Joseon",
    "earth_rhythm":     "Earth Rhythm",
    "juicy_chemistry":  "Juicy Chemistry",
    "quench_botanics":  "Quench Botanics",
    "reequil":          "Re'equil",
    "fae_beauty":       "FAE Beauty",
    "be_bodywise":      "Be Bodywise",
}

# Brands that are unlikely to be on Nykaa (very niche / international-only D2C)
LIKELY_NOT_ON_NYKAA = {
    "beauty_by_boe",    # very niche
    "hibiscus_monkey",  # very niche
    "embryolisse",      # French brand, India D2C but likely not on Nykaa
    "pure_earth",       # niche
    "suhi_and_sego",    # very new
    "raise_beauty",     # very new
    "the_dearist",      # niche
    "the_formula_rx",   # very niche
    "putsimply",        # very new
    "brwn",             # very niche
    "dabtofab",         # new
    "beyond_beyond",    # new
    "dyou",             # niche
    "indewild",         # niche
    "innovist",         # niche
    "deyga",            # niche
    "brillare",         # niche haircare-heavy
    "clayco",           # niche
}

# Search URL template — returns JSON with total product count
# Using the Nykaa search API directly (bypasses heavy JS rendering)
_SEARCH_URL = "https://www.nykaa.com/api/2.0/search?q={q}&sort=relevance&ptype=product&limit=1&category=8377"
# Fallback: scrape the search results page __NEXT_DATA__
_SEARCH_PAGE_URL = "https://www.nykaa.com/search/result/?q={q}&ptype=product&sort=relevance&category=8377"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nykaa.com/",
}


def _build_client(scraperapi_key: str = "") -> httpx.AsyncClient:
    kwargs: dict = {"timeout": 30.0, "headers": _HEADERS, "follow_redirects": True}
    if scraperapi_key:
        kwargs["proxy"] = f"http://scraperapi:{scraperapi_key}@proxy-server.scraperapi.com:8001"
        kwargs["verify"] = False
    return httpx.AsyncClient(**kwargs)


def _parse_total(resp_text: str, url: str) -> int | None:
    """Try multiple parsing strategies to extract total product count."""
    # Strategy 1: JSON API response {"response": {"total": N}}
    try:
        data = json.loads(resp_text)
        # Nykaa API v2 format
        total = (data.get("response") or {}).get("total")
        if total is not None:
            return int(total)
        # Alternative: data["data"]["product"]["total"]
        total = ((data.get("data") or {}).get("product") or {}).get("total")
        if total is not None:
            return int(total)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Strategy 2: __NEXT_DATA__ embedded in HTML
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp_text, re.S)
    if m:
        try:
            nd = json.loads(m.group(1))
            # Navigate common Nykaa __NEXT_DATA__ paths
            for path in [
                ["props", "pageProps", "searchResult", "total"],
                ["props", "pageProps", "data", "product", "total"],
                ["props", "pageProps", "response", "total"],
                ["props", "pageProps", "totalProducts"],
            ]:
                node = nd
                try:
                    for key in path:
                        node = node[key]
                    return int(node)
                except (KeyError, TypeError, ValueError):
                    continue
        except (json.JSONDecodeError, TypeError):
            pass

    # Strategy 3: look for "X Products" pattern in HTML
    m = re.search(r'"total"\s*:\s*(\d+)', resp_text)
    if m:
        return int(m.group(1))

    m = re.search(r'(\d+)\s+(?:Products?|products?|results?|Results?)', resp_text)
    if m:
        return int(m.group(1))

    return None


async def nykaa_count(
    slug: str, brand_name: str, client_direct: httpx.AsyncClient, client_proxy: httpx.AsyncClient | None
) -> tuple[int | None, str]:
    """Return (nykaa_product_count, method_used). None = not found / blocked."""
    q = quote(brand_name)
    api_url = _SEARCH_URL.format(q=q)
    page_url = _SEARCH_PAGE_URL.format(q=q)

    for client, label, url in [
        (client_direct, "direct_api",   api_url),
        (client_direct, "direct_page",  page_url),
        *([(client_proxy, "proxy_api",  api_url),
           (client_proxy, "proxy_page", page_url)] if client_proxy else []),
    ]:
        if client is None:
            continue
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                total = _parse_total(resp.text, url)
                if total is not None:
                    return total, label
        except Exception:
            continue

    return None, "blocked"


async def get_db_counts(db_url: str) -> dict[str, int]:
    """Return {brand_name: product_count} from our DB."""
    dsn = db_url.replace("postgresql+psycopg://", "postgresql://")
    conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
    cur = await conn.execute("""
        SELECT b.name, count(*) as cnt
        FROM core.products p
        JOIN core.brands b ON b.id = p.brand_id
        GROUP BY b.name
        ORDER BY b.name
    """)
    rows = await cur.fetchall()
    await conn.close()
    return {r["name"]: r["cnt"] for r in rows}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-proxy", action="store_true", help="Skip ScraperAPI, direct only")
    args = parser.parse_args()

    from scraper.retailers import RETAILERS, RetailerTier
    from app.config import settings

    scraperapi_key = "" if args.no_proxy else settings.scraperapi_key

    # Only check D2C brands (skip marketplace entries like nykaa, tira, purplle)
    d2c_brands = [
        r for r in RETAILERS
        if r.tier in (RetailerTier.SHOPIFY, RetailerTier.CUSTOM)
    ]

    db_counts = await get_db_counts(settings.database_url)

    print(f"\n{'Brand':<28} {'Our DB':>7} {'Nykaa':>7} {'Coverage':>10}  Method")
    print("─" * 72)

    results: list[dict] = []

    async with _build_client() as direct, _build_client(scraperapi_key) as proxy:
        proxy_client = proxy if scraperapi_key else None

        for r in d2c_brands:
            search_name = NYKAA_SEARCH_NAME.get(r.slug, r.name)
            db_cnt = db_counts.get(r.name, 0)

            if r.slug in LIKELY_NOT_ON_NYKAA:
                print(f"  {r.name:<26} {db_cnt:>7}  {'–':>7}  {'–':>10}  skipped (niche)")
                results.append({"brand": r.name, "slug": r.slug, "db": db_cnt, "nykaa": None, "method": "skipped"})
                continue

            nykaa_cnt, method = await nykaa_count(r.slug, search_name, direct, proxy_client)

            if nykaa_cnt is None:
                coverage = "blocked"
                results.append({"brand": r.name, "slug": r.slug, "db": db_cnt, "nykaa": None, "method": method})
                print(f"  {r.name:<26} {db_cnt:>7}  {'?':>7}  {'?':>10}  {method}")
            else:
                pct = f"{min(nykaa_cnt, db_cnt) / max(db_cnt, 1) * 100:.0f}%" if db_cnt else "n/a"
                results.append({"brand": r.name, "slug": r.slug, "db": db_cnt, "nykaa": nykaa_cnt, "method": method})
                print(f"  {r.name:<26} {db_cnt:>7}  {nykaa_cnt:>7}  {pct:>10}  {method}")

            await asyncio.sleep(0.3)  # gentle rate limit

    # Summary
    found = [r for r in results if r["nykaa"] is not None]
    not_found = [r for r in results if r["nykaa"] is None and r["method"] != "skipped"]
    skipped = [r for r in results if r["method"] == "skipped"]
    total_nykaa = sum(r["nykaa"] for r in found)
    total_db = sum(r["db"] for r in results)
    # Estimated overlap = products we'd actually find on Nykaa (min of our count vs Nykaa count)
    overlap_est = sum(min(r["db"], r["nykaa"]) for r in found)

    print(f"\n{'─' * 72}")
    print(f"  Brands found on Nykaa: {len(found)}")
    print(f"  Brands blocked/unknown: {len(not_found)}")
    print(f"  Brands skipped (niche): {len(skipped)}")
    print(f"  Total Nykaa products (skincare): {total_nykaa:,}")
    print(f"  Total our DB products:           {total_db:,}")
    print(f"\n  Estimated scrape cost (residential proxy, 25 credits/page):")
    print(f"    Nykaa total products found:   {total_nykaa:>6,}")
    print(f"    Est. catalog overlap (match): {overlap_est:>6,}  (min of DB vs Nykaa per brand)")
    print(f"    URL discovery (1 credit ea):  {overlap_est:>6,} × 1  = {overlap_est:>7,} credits")
    page_credits = overlap_est * 25
    total_est = int((overlap_est + page_credits) * 1.15)
    print(f"    Product page scrapes:         {overlap_est:>6,} × 25 = {page_credits:>7,} credits")
    print(f"    With 15% retry overhead:                     {total_est:>7,} credits")
    print(f"    Hobby plan (100k): {'fits ✅' if total_est <= 100_000 else f'OVER by {total_est - 100_000:,} ❌'}")
    print()

    if not_found:
        print(f"  Blocked brands (need manual check):")
        for r in not_found:
            print(f"    - {r['brand']}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
