"""
Scrape Nykaa for all confirmed brands in our catalog.

For each brand, discovers their Nykaa product URLs, fetches each product page,
parses full metadata (price, rating, description, ingredients, how_to_use,
category, variants, images), and upserts into the DB as Nykaa retailer_listings.

Primary fetch: Smartproxy residential (bandwidth-based, free).
Fallback: --retry-failed uses ScraperAPI standard (1 credit/page) for URLs that
          Smartproxy couldn't get past Akamai.

Failed URLs are written to FAILED_URLS_FILE after every run so they can be
retried without re-discovering.

Usage:
    python -m scripts.scrape_nykaa                       # dry-run (default)
    python -m scripts.scrape_nykaa --execute             # write to DB
    python -m scripts.scrape_nykaa --brands minimalist foxtale
    python -m scripts.scrape_nykaa --limit 20            # max products per brand
    python -m scripts.scrape_nykaa --execute --retry-failed  # retry via ScraperAPI
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
log = structlog.get_logger()

FAILED_URLS_FILE = Path(__file__).resolve().parent.parent / "nykaa_failed_urls.jsonl"

# ── Confirmed brands on Nykaa (from check_nykaa_coverage.py) ─────────────────
# Format: retailer_slug → Nykaa search name
NYKAA_BRANDS: dict[str, str] = {
    "minimalist":        "Minimalist",
    "mcaffeine":         "MCaffeine",
    "dot_and_key":       "Dot & Key",
    "the_derma_co":      "The Derma Co",
    "aqualogica":        "Aqualogica",
    "bare_necessities":  "Bare Necessities",
    "beauty_of_joseon":  "Beauty of Joseon",
    "conscious_chemist": "Conscious Chemist",
    "daughter_earth":    "Daughter Earth",
    "dermalogica_in":    "Dermalogica",
    "pilgrim":           "Pilgrim",
    "dr_sheths":         "Dr. Sheth's",
    "earth_rhythm":      "Earth Rhythm",
    "fae_beauty":        "FAE Beauty",
    "foxtale":           "Foxtale",
    "innisfree_in":      "Innisfree",
    "pixi_in":           "Pixi",
    "juicy_chemistry":   "Juicy Chemistry",
    "kiehls_in":         "Kiehl's",
    "world_of_asaya":    "Asaya",
    "paulas_choice_in":  "Paula's Choice",
    "reequil":           "Re'equil",
    "simple_in":         "Simple",
    "the_deconstruct":   "The Deconstruct",
    "the_face_shop_in":  "The Face Shop",
    "the_pink_foundry":  "The Pink Foundry",
    "fixderma":          "Fixderma",
    "lotus":             "Lotus Herbals",
    "ponds_in":          "Pond's",
    "forest_essentials": "Forest Essentials",
    "kama_ayurveda":     "Kama Ayurveda",
    "cetaphil_in":       "Cetaphil",
    "neutrogena_in":     "Neutrogena",
    "mamaearth":         "Mamaearth",
    "nathabit":          "Nathabit",
    "be_bodywise":       "Be Bodywise",
    "plix":              "Plix",
    "thebodyshop_in":    "The Body Shop",
    "olay_in":           "Olay",
    "cerave_in":         "CeraVe",
    "bioderma_in":       "Bioderma",
}

_PRODUCT_PAGE_DELAY = 2.0  # seconds between product page fetches (Akamai evasion)


async def _get_conn(db_url: str) -> psycopg.AsyncConnection:
    dsn = db_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)


async def run_brand(
    slug: str,
    search_name: str,
    limit: int,
    dry_run: bool,
    db_url: str | None,
    retailer_id: int,
    proxy_url: str,
    proxy_user: str,
    proxy_pass: str,
    scraperapi_key: str,
) -> tuple[int, list[dict]]:
    """Returns (upserted_count, failed_items) where failed_items are dicts with url/name/brand."""
    from scraper.fetchers.nykaa import fetch_nykaa_brand_product_urls, fetch_nykaa_page
    from scraper.parsers.nykaa import parse_nykaa_product
    from scraper.db import upsert_product
    from scraper.retailers import retailer_by_slug

    retailer = retailer_by_slug("nykaa")
    log.info("nykaa_brand_start", brand=slug, search_name=search_name)

    discovered = await fetch_nykaa_brand_product_urls(
        search_name, scraperapi_key, limit=limit
    )
    if not discovered:
        log.warning("nykaa_brand_no_urls", brand=slug)
        return 0, []

    log.info("nykaa_brand_urls_found", brand=slug, count=len(discovered))

    if dry_run:
        for d in discovered[:3]:
            log.info("nykaa_dry_run_sample", brand=slug, url=d["url"], name=d["name"])
        return len(discovered), []

    conn = await _get_conn(db_url)
    ok = 0
    failed: list[dict] = []

    try:
        for i, item in enumerate(discovered):
            url = item["url"]
            html = await fetch_nykaa_page(url, proxy_url, proxy_user, proxy_pass)
            if not html:
                log.warning("nykaa_page_fetch_failed", brand=slug, url=url)
                failed.append({"url": url, "name": item.get("name", ""), "brand": slug})
                await asyncio.sleep(_PRODUCT_PAGE_DELAY)
                continue

            product = parse_nykaa_product(html, url)
            if not product.canonical_name:
                log.warning("nykaa_parse_no_name", brand=slug, url=url)
                await asyncio.sleep(_PRODUCT_PAGE_DELAY)
                continue

            try:
                await upsert_product(conn, product, retailer, retailer_id)
                ok += 1
            except Exception as exc:
                log.error("nykaa_upsert_error", brand=slug, name=product.canonical_name, error=str(exc))
                # Try to recover; if connection is lost, open a fresh one
                try:
                    await conn.rollback()
                except Exception:
                    log.warning("nykaa_conn_lost_reconnecting", brand=slug)
                    try:
                        await conn.close()
                    except Exception:
                        pass
                    conn = await _get_conn(db_url)

            if (i + 1) % 20 == 0:
                log.info("nykaa_brand_progress", brand=slug, done=i + 1, total=len(discovered),
                         upserted=ok, failed=len(failed))
            await asyncio.sleep(_PRODUCT_PAGE_DELAY)
    finally:
        try:
            await conn.close()
        except Exception:
            pass

    log.info("nykaa_brand_done", brand=slug, upserted=ok, failed=len(failed), total=len(discovered))
    return ok, failed


async def run_retry_failed(
    conn,
    retailer_id: int,
    scraperapi_key: str,
) -> int:
    """Retry failed URLs from FAILED_URLS_FILE using ScraperAPI standard (1 credit/page)."""
    from scraper.fetchers.nykaa import fetch_nykaa_page_scraperapi
    from scraper.parsers.nykaa import parse_nykaa_product
    from scraper.db import upsert_product
    from scraper.retailers import retailer_by_slug

    if not FAILED_URLS_FILE.exists():
        log.warning("no_failed_urls_file", path=str(FAILED_URLS_FILE))
        return 0

    items = [json.loads(line) for line in FAILED_URLS_FILE.read_text().splitlines() if line.strip()]
    log.info("nykaa_retry_start", count=len(items))

    retailer = retailer_by_slug("nykaa")
    ok = 0
    still_failed: list[dict] = []

    for i, item in enumerate(items):
        url = item["url"]
        html = await fetch_nykaa_page_scraperapi(url, scraperapi_key)
        if not html:
            still_failed.append(item)
            await asyncio.sleep(1.0)
            continue

        product = parse_nykaa_product(html, url)
        if not product.canonical_name:
            log.warning("nykaa_retry_parse_no_name", url=url)
            await asyncio.sleep(1.0)
            continue

        try:
            await upsert_product(conn, product, retailer, retailer_id)
            ok += 1
        except Exception as exc:
            log.error("nykaa_retry_upsert_error", name=product.canonical_name, error=str(exc))
            await conn.rollback()
            still_failed.append(item)

        if (i + 1) % 20 == 0:
            log.info("nykaa_retry_progress", done=i + 1, total=len(items), upserted=ok)
        await asyncio.sleep(1.0)

    # Overwrite file with items that still failed
    if still_failed:
        FAILED_URLS_FILE.write_text("\n".join(json.dumps(x) for x in still_failed) + "\n")
        log.warning("nykaa_retry_still_failed", count=len(still_failed))
    else:
        FAILED_URLS_FILE.unlink(missing_ok=True)

    log.info("nykaa_retry_done", upserted=ok, still_failed=len(still_failed))
    return ok


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Write to DB (default: dry-run)")
    parser.add_argument("--brands", nargs="*", help="Retailer slugs to scrape (default: all confirmed)")
    parser.add_argument("--limit", type=int, default=300, help="Max products per brand (default: 300)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Only retry previously saved failed URLs via ScraperAPI (skip full brand scrape)")
    args = parser.parse_args()

    from app.config import settings
    from scraper.db import ensure_retailers

    dry_run = not args.execute

    if args.retry_failed:
        if dry_run:
            log.error("retry_failed_requires_execute")
            return
        conn = await _get_conn(settings.database_url)
        try:
            retailer_ids = await ensure_retailers(conn)
            nykaa_retailer_id = retailer_ids.get("nykaa", 0)
            await run_retry_failed(conn, nykaa_retailer_id, settings.scraperapi_key)
        finally:
            await conn.close()
        return

    brands = {
        slug: name
        for slug, name in NYKAA_BRANDS.items()
        if not args.brands or slug in args.brands
    }

    if not brands:
        log.error("no_matching_brands")
        return

    proxy_url = settings.proxy_url
    proxy_user = settings.proxy_user
    proxy_pass = settings.proxy_pass

    if not proxy_url or not proxy_user or not proxy_pass:
        log.error("smartproxy_not_configured",
                  hint="Set PROXY_URL, PROXY_USER, PROXY_PASS in .env")
        return

    log.info("nykaa_scrape_start",
             brands=list(brands.keys()), dry_run=dry_run, limit=args.limit)

    # Resolve retailer ID once with a short-lived connection
    nykaa_retailer_id = 0
    if not dry_run:
        conn0 = await _get_conn(settings.database_url)
        try:
            retailer_ids = await ensure_retailers(conn0)
            nykaa_retailer_id = retailer_ids.get("nykaa", 0)
        finally:
            await conn0.close()

    total = 0
    all_failed: list[dict] = []
    fatal_brands: list[str] = []

    db_url = settings.database_url if not dry_run else None

    for slug, search_name in brands.items():
        try:
            brand_total, brand_failed = await run_brand(
                slug, search_name, args.limit, dry_run,
                db_url, nykaa_retailer_id,
                proxy_url, proxy_user, proxy_pass,
                scraperapi_key=settings.scraperapi_key,
            )
            total += brand_total
            all_failed.extend(brand_failed)
        except Exception as exc:
            log.error("nykaa_brand_fatal", brand=slug, error=str(exc))
            fatal_brands.append(slug)

    # ── Auto-retry brands that crashed (e.g. connection drop) ────────────────
    if fatal_brands and not dry_run:
        log.info("nykaa_retrying_fatal_brands", brands=fatal_brands, count=len(fatal_brands))
        for slug in fatal_brands:
            search_name = brands[slug]
            try:
                brand_total, brand_failed = await run_brand(
                    slug, search_name, args.limit, dry_run,
                    db_url, nykaa_retailer_id,
                    proxy_url, proxy_user, proxy_pass,
                    scraperapi_key=settings.scraperapi_key,
                )
                total += brand_total
                all_failed.extend(brand_failed)
                log.info("nykaa_fatal_brand_recovered", brand=slug, upserted=brand_total)
            except Exception as exc:
                log.error("nykaa_fatal_brand_retry_failed", brand=slug, error=str(exc))

    # ── Persist failed URLs ───────────────────────────────────────────────────
    if all_failed and not dry_run:
        existing: list[dict] = []
        if FAILED_URLS_FILE.exists():
            existing = [json.loads(l) for l in FAILED_URLS_FILE.read_text().splitlines() if l.strip()]
        existing_urls = {x["url"] for x in existing}
        new_failures = [x for x in all_failed if x["url"] not in existing_urls]
        combined = existing + new_failures
        FAILED_URLS_FILE.write_text("\n".join(json.dumps(x) for x in combined) + "\n")
        log.info("nykaa_failed_urls_saved", count=len(combined), path=str(FAILED_URLS_FILE))

    # ── Auto-retry Akamai-blocked URLs via ScraperAPI ─────────────────────────
    if all_failed and not dry_run:
        if not settings.scraperapi_key:
            log.warning("nykaa_scraperapi_not_configured",
                        hint="Set SCRAPERAPI_KEY in .env to auto-retry Akamai-blocked URLs")
        else:
            log.info("nykaa_auto_retry_start", failed_count=len(all_failed))
            conn_retry = await _get_conn(settings.database_url)
            try:
                await run_retry_failed(conn_retry, nykaa_retailer_id, settings.scraperapi_key)
            finally:
                await conn_retry.close()

    log.info("nykaa_scrape_complete", total=total, failed=len(all_failed),
             fatal_brands=fatal_brands, dry_run=dry_run)


if __name__ == "__main__":
    asyncio.run(main())
