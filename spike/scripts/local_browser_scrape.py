"""Local browser scraper for the spike — no proxy, face skincare only.

Navigates marketplace category pages like a human, discovers product URLs,
visits each, and saves HTML to data/raw/<retailer>/<id>.html.
Run this, then run build_reports.py to get the field-matrix.

Usage:
  cd spike
  python scripts/local_browser_scrape.py                  # all marketplaces
  python scripts/local_browser_scrape.py --retailer nykaa # one retailer
  python scripts/local_browser_scrape.py --dry            # print URLs, no fetch
"""
from __future__ import annotations

import argparse
import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path

import structlog
from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

from spike.models import ParsedSample, RawCapture
from spike.samplers.base import persist_parsed, persist_raw
from spike.samplers.marketplace import parse_marketplace_html

SPIKE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SPIKE_ROOT / ".env")
log = structlog.get_logger()

# Face skincare category entry points — one per marketplace.
# The scraper navigates here, extracts product URLs, then visits each.
FACE_CATEGORY_URLS: dict[str, list[str]] = {
    "nykaa": [
        "https://www.nykaa.com/beauty/skin/face-serums/c/1205?sortby=popularity",
        "https://www.nykaa.com/beauty/skin/moisturizers-and-creams/face-moisturiser/c/1217?sortby=popularity",
        "https://www.nykaa.com/beauty/skin/face-wash-and-cleansers/c/1237?sortby=popularity",
    ],
    "amazon_in": [
        "https://www.amazon.in/s?k=face+serum&i=beauty&rh=n%3A1355016031&s=review-rank",
        "https://www.amazon.in/s?k=face+moisturizer&i=beauty&rh=n%3A1355016031&s=review-rank",
        "https://www.amazon.in/s?k=face+wash+india&i=beauty&rh=n%3A1355016031&s=review-rank",
    ],
    "tira": [
        "https://www.tirabeauty.com/category/face-serum-46",
        "https://www.tirabeauty.com/category/face-moisturiser-45",
        "https://www.tirabeauty.com/category/face-wash-cleanser-44",
    ],
    "purplle": [
        "https://www.purplle.com/skin-care/face-serum?sort=popular",
        "https://www.purplle.com/skin-care/face-moisturiser?sort=popular",
        "https://www.purplle.com/skin-care/face-wash?sort=popular",
    ],
}

# CSS selectors to find product links on category/search pages.
# Each entry is tried in order; first one that yields URLs wins.
PRODUCT_LINK_SELECTORS: dict[str, list[str]] = {
    "nykaa": [
        "a.css-qlopj4",           # product card link (primary)
        "a[href*='/p/']",         # fallback: any link with /p/ (product detail pattern)
    ],
    "amazon_in": [
        "a.a-link-normal.s-no-outline",
        "h2 a.a-link-normal",
        "a[href*='/dp/']",         # ASIN links
    ],
    "tira": [
        "a.product-card__link",
        "a[href*='/product/']",
        "a[href*='/p/']",
    ],
    "purplle": [
        "a.product-card-link",
        "a[href*='/beauty/']",
        "a.jsx-product-card",
    ],
}

# Max products per retailer for the spike (face-only).
MAX_PER_RETAILER = 10
# Delay range between page loads (seconds) — mimics human reading time.
DELAY_RANGE = (3.0, 7.0)


async def human_delay(page: Page, extra: float = 0.0) -> None:
    """Random dwell + scroll to mimic human behaviour."""
    await asyncio.sleep(random.uniform(*DELAY_RANGE) + extra)
    # Scroll down partway to trigger lazy-loading.
    await page.evaluate("window.scrollBy(0, Math.random() * 600 + 300)")
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await page.evaluate("window.scrollBy(0, Math.random() * 400 + 200)")
    await asyncio.sleep(random.uniform(0.3, 0.8))


async def discover_product_urls(
    page: Page, category_urls: list[str], selectors: list[str], max_n: int, base_url: str
) -> list[str]:
    """Navigate category pages, extract unique product URLs."""
    found: list[str] = []
    seen: set[str] = set()

    for cat_url in category_urls:
        if len(found) >= max_n:
            break
        log.info("navigating_category", url=cat_url)
        try:
            await page.goto(cat_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(page, extra=2.0)  # extra wait for JS to render product grid
        except Exception as e:
            log.warning("category_nav_failed", url=cat_url, error=str(e))
            continue

        for selector in selectors:
            hrefs = await page.eval_on_selector_all(
                selector, "els => els.map(e => e.href || e.getAttribute('href'))"
            )
            for href in hrefs:
                if not href:
                    continue
                # Make relative URLs absolute.
                if href.startswith("/"):
                    href = base_url.rstrip("/") + href
                # Dedupe and skip non-product URLs.
                if href in seen:
                    continue
                if any(skip in href for skip in ["javascript:", "#", "?", "signin", "login", "cart"]):
                    continue
                seen.add(href)
                found.append(href)
                if len(found) >= max_n:
                    break
            if found:
                break  # first selector that yielded results wins for this page

    log.info("discovered_urls", count=len(found))
    return found[:max_n]


async def scrape_product_page(
    page: Page,
    url: str,
    retailer_slug: str,
    raw_dir: Path,
    parsed_dir: Path,
) -> ParsedSample | None:
    log.info("scraping_product", retailer=retailer_slug, url=url)
    status = 0
    body = ""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        status = resp.status if resp else 0
        await human_delay(page)
        body = await page.content()
    except Exception as e:
        log.warning("product_fetch_failed", url=url, error=str(e))
        return None

    if not body or status >= 400:
        log.warning("product_bad_response", url=url, status=status)
        return None

    # Persist raw HTML.
    rc = RawCapture(
        retailer_slug=retailer_slug,
        source_url=url,
        tier_used="marketplace-selector",
        fetched_at=datetime.now(timezone.utc),
        fetcher_version="spike-local-browser-0.0.1",
        content_type="text/html",
        body=body,
        http_status=status,
    )
    cid = persist_raw(rc, raw_dir)

    # Parse and persist.
    ps = parse_marketplace_html(
        html=body,
        retailer_slug=retailer_slug,
        source_url=url,
        raw_capture_id=cid,
    )
    persist_parsed(ps, parsed_dir)
    log.info(
        "scraped_product",
        retailer=retailer_slug,
        name=ps.canonical_name,
        price=ps.current_price,
        missing=sorted(ps.missing_fields),
    )
    return ps


BASE_URLS = {
    "nykaa": "https://www.nykaa.com",
    "amazon_in": "https://www.amazon.in",
    "tira": "https://www.tirabeauty.com",
    "purplle": "https://www.purplle.com",
}


async def scrape_retailer(
    retailer_slug: str, raw_dir: Path, parsed_dir: Path, dry: bool
) -> list[ParsedSample]:
    cat_urls = FACE_CATEGORY_URLS[retailer_slug]
    selectors = PRODUCT_LINK_SELECTORS[retailer_slug]
    base_url = BASE_URLS[retailer_slug]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        # Discovery page.
        disc_page = await context.new_page()
        product_urls = await discover_product_urls(
            disc_page, cat_urls, selectors, MAX_PER_RETAILER, base_url
        )
        await disc_page.close()

        if dry:
            log.info("dry_run_urls", retailer=retailer_slug, urls=product_urls)
            await browser.close()
            return []

        if not product_urls:
            log.warning("no_product_urls_found", retailer=retailer_slug)
            await browser.close()
            return []

        # Scrape each product URL.
        samples: list[ParsedSample] = []
        for url in product_urls:
            prod_page = await context.new_page()
            sample = await scrape_product_page(prod_page, url, retailer_slug, raw_dir, parsed_dir)
            await prod_page.close()
            if sample:
                samples.append(sample)
            # Extra delay between products.
            await asyncio.sleep(random.uniform(2.0, 4.0))

        await browser.close()
    return samples


async def main(retailers: list[str], dry: bool) -> None:
    raw_dir = SPIKE_ROOT / "data" / "raw"
    parsed_dir = SPIKE_ROOT / "data" / "parsed"

    for retailer_slug in retailers:
        log.info("starting_retailer", retailer=retailer_slug)
        samples = await scrape_retailer(retailer_slug, raw_dir, parsed_dir, dry)
        log.info("retailer_done", retailer=retailer_slug, scraped=len(samples))

    if not dry:
        total = sum(1 for _ in parsed_dir.glob("*/*.json"))
        log.info("all_done", total_parsed_samples=total)
        print(f"\nDone. {total} parsed samples in {parsed_dir}")
        print(f"Now run: python scripts/build_reports.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Local browser scraper — face skincare spike")
    ap.add_argument(
        "--retailer",
        choices=list(FACE_CATEGORY_URLS.keys()),
        help="Scrape one retailer only (default: all)",
    )
    ap.add_argument(
        "--dry",
        action="store_true",
        help="Discover product URLs but don't fetch product pages",
    )
    args = ap.parse_args()

    target_retailers = [args.retailer] if args.retailer else list(FACE_CATEGORY_URLS.keys())
    asyncio.run(main(target_retailers, dry=args.dry))
