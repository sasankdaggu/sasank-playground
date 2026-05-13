"""Run LLM-based ingredient schema detection for brand websites.

Detects and stores per-brand CSS selectors for INCI ingredient extraction.
Run monthly or when ingredient extraction failures spike.

Usage:
  python -m scraper.run_schema_detection                          # all brands
  python -m scraper.run_schema_detection --brands mamaearth.in   # specific brand(s)
  python -m scraper.run_schema_detection --status pending         # only pending brands
  python -m scraper.run_schema_detection --status failed needs_review  # retry failures
  python -m scraper.run_schema_detection --dry-run                # discover URLs, no DB writes
  python -m scraper.run_schema_detection --concurrency 5          # parallel workers
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app.config import settings  # noqa: E402
from scraper.ingredient_schema_detector import (  # noqa: E402
    detect_brand_strategy,
    upsert_strategy,
)

log = structlog.get_logger()

# ── Brand registry — all D2C brands for Wand Phase 1 ──────────────────────────
# Marketplace-only brands (CosRX, Laneige, etc.) are deferred — they require
# Nykaa/Sephora product page scraping via proxy (Phase 2).

BRAND_REGISTRY: list[tuple[str, str]] = [
    # (brand_name, homepage_url)
    # ── Original 5 (already in retailers table, strategies can be pre-populated) ──
    ("Minimalist",          "https://beminimalist.co"),
    ("Plum Goodness",       "https://plumgoodness.com"),
    ("mCaffeine",           "https://www.mcaffeine.com"),
    ("Dot & Key",           "https://www.dotandkey.com"),
    ("The Derma Co",        "https://thedermaco.com"),
    # ── New brands (alphabetical) ──
    ("82e",                 "https://82e.com"),
    ("Aqualogica",          "https://aqualogica.in"),
    ("Aveeno India",        "https://www.aveeno.in"),
    ("Bare Necessities",    "https://barenecessities.in"),
    ("Be Bodywise",         "https://bebodywise.com"),
    ("Beauty of Joseon",    "https://beautyofjoseon.com"),
    ("Beauty by Bie",       "https://beautybybie.com"),
    ("Beyond Beyond",       "https://beyondbeyond.co.in"),
    ("Bioderma India",      "https://www.bioderma-india.in"),
    ("Brillare",            "https://www.brillare.co.in"),
    ("BRWN",                "https://brwn.in"),
    ("Cetaphil India",      "https://www.cetaphil.in"),
    ("CeraVe India",        "https://www.ceraveindia.com"),
    ("ClayC",               "https://clayco.in"),
    ("Conscious Chemist",   "https://consciouschemist.com"),
    ("Dab to Fab",          "https://dabtofab.co"),
    ("Daughter Earth",      "https://daughter.earth"),
    ("Dermalogica India",   "https://dermalogica.in"),
    ("Deyga",               "https://deyga.in"),
    ("Discoverpilgrim",     "https://discoverpilgrim.com"),
    ("Dr. Sheth's",         "https://www.drsheths.com"),
    ("D'You",               "https://www.dyou.co"),
    ("Earth Rhythm",        "https://earthrhythm.com"),
    ("Embryolisse",         "https://myembryolisse.com"),
    ("FAE Beauty",          "https://www.faebeauty.in"),
    ("Fixderma",            "https://www.fixderma.com"),
    ("Forest Essentials",   "https://www.forestessentialsindia.com"),
    ("Foxtale",             "https://foxtale.in"),
    ("Garnier India",       "https://www.garnier.in"),
    ("Hibiscus Monkey",     "https://www.hibiscusmonkey.com"),
    ("Himalaya",            "https://himalayawellness.in"),
    ("India Indewild",      "https://india.indewild.com"),
    ("Innisfree India",     "https://in.innisfree.com"),
    ("Innovist",            "https://innovist.com"),
    ("Juicy Chemistry",     "https://juicychemistry.com"),
    ("Kama Ayurveda",       "https://www.kamaayurveda.in"),
    ("Kiehl's India",       "https://www.kiehls.in"),
    ("Lakme India",         "https://www.lakmeindia.com"),
    ("Let's Hyphen",        "https://letshyphen.com"),
    ("Lotus",               "https://www.lotus.in"),
    ("Mamaearth",           "https://mamaearth.in"),
    ("Nathabit",            "https://nathabit.in"),
    ("Neutrogena India",    "https://www.neutrogena.in"),
    ("Olay India",          "https://www.olayskincare.com/en-in"),
    ("Paula's Choice India","https://www.paulaschoice.in"),
    ("Pixi Beauty India",   "https://in.pixibeauty.com"),
    ("Plix Life",           "https://www.plixlife.com"),
    ("Ponds India",         "https://ponds.in"),
    ("Pure Arth Asia",      "https://india.purearth.asia"),
    ("Put Simply",          "https://putsimply.co.in"),
    ("Quench Botanics",     "https://www.quenchbotanics.com"),
    ("Raise Beauty",        "https://raisebeauty.com"),
    ("Re'equil",            "https://www.reequil.com"),
    ("Simple Skincare",     "https://www.simpleskincare.in"),
    ("Suhi & Sego",         "https://www.suhiandsego.com"),
    ("The Body Shop India", "https://www.thebodyshop.in"),
    ("The Dearist",         "https://www.thedearist.com"),
    ("The Deconstruct",     "https://thedeconstruct.in"),
    ("The Face Shop India", "https://thefaceshop.in"),
    ("The Formula RX",      "https://theformularx.com"),
    ("The Pink Foundry",    "https://www.thepinkfoundry.com"),
    # Tony Moly D2C site (tonymoly.in) does not resolve — Nykaa only, see MARKETPLACE_ONLY_BRANDS
    # ("Tony Moly",           "https://tonymoly.in"),
    ("World of Asaya",      "https://worldofasaya.com"),
]

# Marketplace-only brands — deferred to Phase 2 (need Nykaa/Sephora scraping)
MARKETPLACE_ONLY_BRANDS = [
    ("CosRX",      "Nykaa"),
    ("Laneige",    "Nykaa"),
    ("Clinique",   "Nykaa"),
    ("The Ordinary", "Sephora India"),
    ("OUAI",       "Sephora India"),
    ("Tony Moly",  "Nykaa"),
    ("Celimax",    "Nykaa"),
    ("Anua",       "Nykaa"),
    ("Q+A",        "Nykaa"),
    ("Olaplex",    "Nykaa"),
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LLM-based ingredient schema detection for brand websites")
    p.add_argument("--brands", nargs="*",
                   help="Brand domains to detect (e.g. mamaearth.in beminimalist.co). Default: all.")
    p.add_argument("--status", nargs="*",
                   choices=["pending", "failed", "needs_review", "active", "no_inci"],
                   help="Only process brands with these DB statuses (default: pending only)")
    p.add_argument("--all", action="store_true",
                   help="Process all brands regardless of current status")
    p.add_argument("--dry-run", action="store_true",
                   help="Discover sample URLs and detect, but skip DB writes")
    p.add_argument("--concurrency", type=int, default=3,
                   help="Number of parallel detection workers (default: 3)")
    return p.parse_args()


async def _get_conn() -> psycopg.AsyncConnection:
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)


async def _get_existing_statuses(conn, domains: list[str]) -> dict[str, str]:
    """Return domain → status map for brands already in the DB."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT brand_domain, status FROM scraping.ingredient_strategies WHERE brand_domain = ANY(%s)",
            (domains,),
        )
        return {r["brand_domain"]: r["status"] for r in await cur.fetchall()}


async def _worker(
    sem: asyncio.Semaphore,
    brand_name: str,
    brand_url: str,
    api_key: str,
    dry_run: bool,
    conn,
    results: dict,
) -> None:
    async with sem:
        try:
            result = await detect_brand_strategy(brand_url, brand_name, api_key)
            if not dry_run and conn:
                await upsert_strategy(conn, result)
            results[result.status] = results.get(result.status, 0) + 1
            log.info("brand_detection_done",
                     brand=brand_name, status=result.status,
                     selector=result.css_selector,
                     preview=result.sample_inci_preview[:60] if result.sample_inci_preview else None)
        except Exception as exc:
            log.error("brand_detection_error", brand=brand_name, error=str(exc))
            results["error"] = results.get("error", 0) + 1
        # Be polite — don't hammer brand sites in rapid succession
        await asyncio.sleep(1)


async def main() -> None:
    args = _parse_args()

    if not settings.anthropic_api_key:
        log.error("anthropic_api_key_required",
                  msg="Set ANTHROPIC_API_KEY in .env — needed for LLM schema detection")
        return

    # Determine which brands to process
    target_brands = BRAND_REGISTRY
    if args.brands:
        # Filter by domain substring match
        target_brands = [
            (name, url) for name, url in BRAND_REGISTRY
            if any(b in url for b in args.brands)
        ]

    conn = None if args.dry_run else await _get_conn()

    try:
        if not args.dry_run and not args.all and conn:
            # Filter by status
            target_statuses = set(args.status or ["pending"])
            domains = [_extract_domain(url) for _, url in target_brands]
            existing = await _get_existing_statuses(conn, domains)

            filtered = []
            for name, url in target_brands:
                domain = _extract_domain(url)
                current_status = existing.get(domain, "pending")
                if current_status in target_statuses:
                    filtered.append((name, url))
            target_brands = filtered

        if not target_brands:
            log.info("no_brands_to_process")
            return

        log.info("schema_detection_start",
                 total=len(target_brands), dry_run=args.dry_run,
                 concurrency=args.concurrency)

        sem = asyncio.Semaphore(args.concurrency)
        results: dict[str, int] = {}

        tasks = [
            _worker(sem, name, url, settings.anthropic_api_key, args.dry_run, conn, results)
            for name, url in target_brands
        ]
        await asyncio.gather(*tasks)

        log.info("schema_detection_complete", results=results)

    finally:
        if conn:
            await conn.close()


def _extract_domain(url: str) -> str:
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lstrip("www.") or url


if __name__ == "__main__":
    asyncio.run(main())
