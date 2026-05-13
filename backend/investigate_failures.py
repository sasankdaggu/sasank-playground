"""
Investigate ingredient extraction failures for earth_rhythm, bioderma_in, kiehls_in, neutrogena_in.
"""
import asyncio
import re
import sys
sys.path.insert(0, '/Users/sdagguba/sasank-playground/backend')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/Users/sdagguba/sasank-playground/backend/.env'))

import psycopg
import psycopg.rows
import httpx
from app.config import settings

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

BRANDS = ["earth_rhythm", "bioderma_in", "kiehls_in", "neutrogena_in"]

QUERY = """
SELECT p.canonical_name, rl.listing_url
FROM scraping.ingredient_extraction_queue q
JOIN core.retailer_listings rl ON rl.id = q.listing_id
JOIN core.products p ON p.id = q.product_id
JOIN core.retailers r ON r.id = rl.retailer_id
LEFT JOIN scraping.ingredient_strategies s ON r.base_url LIKE ('%%' || s.brand_domain || '%%')
WHERE r.slug = %s AND q.status = 'failed'
ORDER BY p.canonical_name
"""

async def fetch_page(url: str):
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url)
            return resp.text, resp.status_code
    except Exception as e:
        return "", str(e)


def check_kiehls_selector(html: str) -> str:
    """Check what .ingredients-popup-inner returns for Kiehl's."""
    m = re.search(
        r'<div[^>]*class="[^"]*ingredients-popup-inner[^"]*"[^>]*>(.*?)</div\s*>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        # Check broader popup context
        m2 = re.search(r'ingredients-popup', html, re.IGNORECASE)
        if m2:
            chunk = html[m2.start():m2.start()+2000]
            clean = re.sub(r'<[^>]+>', ' ', chunk)
            clean = ' '.join(clean.split())[:300]
            return f"DIV NOT FOUND but popup exists: {clean}"
        return "SELECTOR NOT FOUND — .ingredients-popup-inner absent from page"
    text = re.sub(r'<[^>]+>', '', m.group(1))
    text = ' '.join(text.split()).strip()
    return f"FOUND (len={len(text)}): {text[:300]}"


def check_kiehls_popup_structure(html: str) -> str:
    """Check full ingredients-popup structure."""
    results = []
    for pat in ['ingredients-popup', 'ingredient-popup', 'ingredients__popup',
                'product-ingredients', 'full-ingredients', 'ingredient-list']:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            chunk = html[m.start():m.start()+1500]
            # find text content
            clean = re.sub(r'<[^>]+>', ' ', chunk)
            clean = ' '.join(clean.split())[:250]
            results.append(f"'{pat}': {clean}")
    return "\n    ".join(results) if results else "NO INGREDIENT POPUP STRUCTURE"


def check_bioderma_ingredients(html: str) -> str:
    """Check Bioderma ingredient selector — Drupal-based site."""
    results = []
    # Common Drupal field patterns
    for pat in [
        r'field[_-]ingredient',
        r'composants?',
        r'ingredient',
        r'field--name.*ingredient',
        r'INCI',
    ]:
        for m in re.finditer(pat, html, re.IGNORECASE):
            start = max(0, m.start() - 50)
            end = min(len(html), m.end() + 400)
            snippet = re.sub(r'<[^>]+>', ' ', html[start:end])
            snippet = ' '.join(snippet.split())[:250]
            results.append(f"Pattern '{pat}': ...{snippet}...")
            break  # only first match per pattern
    return "\n    ".join(results) if results else "NO INGREDIENT PATTERN FOUND"


def is_bundle_or_set(name: str, html: str) -> str:
    """Identify if product is a bundle/gift set."""
    name_lower = name.lower()
    bundle_keywords = ['kit', 'pack ', 'set', 'duo', 'bundle', 'combo', 'gift', 'trio', 'routine']
    for kw in bundle_keywords:
        if kw in name_lower:
            return f"YES — '{kw}' in name"
    # Check HTML too
    for kw in ['gift set', 'bundle', 'combo', 'starter kit']:
        if re.search(kw, html[:5000], re.IGNORECASE):
            return f"POSSIBLY — '{kw}' in page HTML"
    return "No"


def check_earth_rhythm_structure(html: str) -> str:
    """Check Earth Rhythm ingredient structure."""
    results = []
    # Earth Rhythm is a custom D2C (not Shopify), check multiple patterns
    for pat in [
        r'ingredients',
        r'Aqua',
        r'accordion',
        r'tab-content',
        r'product-description',
        r'product__description',
        r'metafield',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 30)
            end = min(len(html), m.end() + 400)
            snippet = re.sub(r'<[^>]+>', ' ', html[start:end])
            snippet = ' '.join(snippet.split())[:250]
            results.append(f"'{pat}': {snippet}")
    return "\n    ".join(results[:5]) if results else "NO INGREDIENT PATTERN FOUND"


async def get_brand_strategy(conn, brand_slug: str) -> dict:
    """Get the ingredient strategy for a brand."""
    rows = await conn.execute("""
        SELECT s.*
        FROM scraping.ingredient_strategies s
        JOIN core.retailers r ON r.base_url LIKE ('%%' || s.brand_domain || '%%')
        WHERE r.slug = %s
    """, (brand_slug,))
    result = await rows.fetchone()
    return dict(result) if result else {}


async def investigate_brand(conn, brand_slug: str):
    print(f"\n{'='*70}")
    print(f"BRAND: {brand_slug}")
    print('='*70)

    # Get strategy
    strategy = await get_brand_strategy(conn, brand_slug)
    if strategy:
        print(f"Strategy: css_selector={strategy.get('css_selector')}, "
              f"requires_js={strategy.get('requires_js')}, status={strategy.get('status')}")
    else:
        print("Strategy: NOT FOUND")

    rows = await conn.execute(QUERY, (brand_slug,))
    failed = await rows.fetchall()

    if not failed:
        print("  No failed products found.")
        return

    print(f"\nTotal failed: {len(failed)}")
    print("\nAll failed products:")
    for i, row in enumerate(failed, 1):
        print(f"  {i:2}. {row['canonical_name']}")

    if brand_slug == "neutrogena_in":
        print("\n[NEUTROGENA] Confirming ScraperAPI dependency...")
        for row in failed[:2]:
            url = row['listing_url']
            print(f"\n  Checking: {row['canonical_name']}")
            print(f"  URL: {url}")
            html, status = await fetch_page(url)
            if isinstance(status, int):
                print(f"  Direct fetch: HTTP {status}, size={len(html)} bytes")
                if len(html) < 600:
                    clean = re.sub(r'<[^>]+>', ' ', html)
                    print(f"  Response: {' '.join(clean.split())[:200]}")
                else:
                    # Check if it's a real page or CDN error
                    if re.search(r'Cloudflare|Access Denied|403|captcha', html[:2000], re.IGNORECASE):
                        print(f"  -> CDN BLOCKED (Cloudflare/Access Denied in response)")
                    else:
                        print(f"  -> Page loaded OK directly? Unexpected!")
            else:
                print(f"  Fetch error: {status}")
        return

    # Fetch 3 sample pages for detailed analysis
    sample_count = min(3, len(failed))
    print(f"\n--- Fetching {sample_count} sample pages for analysis ---")

    for row in failed[:sample_count]:
        name = row['canonical_name']
        url = row['listing_url']
        print(f"\n  Product: {name}")
        print(f"  URL: {url}")

        html, status = await fetch_page(url)

        if not isinstance(status, int):
            print(f"  ERROR: {status}")
            continue
        if status == 404:
            print(f"  HTTP 404 — product page not found (may be discontinued)")
            continue
        if status >= 400:
            print(f"  HTTP {status} — page unavailable")
            continue

        print(f"  Page size: {len(html)} bytes (HTTP {status})")

        if brand_slug == "kiehls_in":
            # Check the current selector
            selector_result = check_kiehls_selector(html)
            print(f"  Current selector (.ingredients-popup-inner): {selector_result}")

            # Check broader popup structure
            popup_struct = check_kiehls_popup_structure(html)
            if popup_struct != "NO INGREDIENT POPUP STRUCTURE":
                print(f"  Popup structures found:\n    {popup_struct}")

            # Check if it's a bundle/set
            bundle = is_bundle_or_set(name, html)
            print(f"  Bundle/Set check: {bundle}")

            # Check if INCI is anywhere on page
            if re.search(r'\bAqua\b', html):
                print(f"  -> 'Aqua' IS present in HTML")
            else:
                print(f"  -> 'Aqua' NOT present in HTML — no INCI on this page")

        elif brand_slug == "bioderma_in":
            # Check bundle/set
            bundle = is_bundle_or_set(name, html)
            print(f"  Bundle/Set: {bundle}")

            # Check ingredient patterns
            ingredient_info = check_bioderma_ingredients(html)
            print(f"  Ingredient patterns:\n    {ingredient_info}")

            # Check if Aqua is present
            if re.search(r'\bAqua\b', html):
                print(f"  -> 'Aqua' IS present in HTML")
            else:
                print(f"  -> 'Aqua' NOT present in HTML")

        elif brand_slug == "earth_rhythm":
            bundle = is_bundle_or_set(name, html)
            print(f"  Bundle/Set: {bundle}")

            struct = check_earth_rhythm_structure(html)
            print(f"  Ingredient structures:\n    {struct}")

            if re.search(r'\bAqua\b', html):
                print(f"  -> 'Aqua' IS present in HTML")
            else:
                print(f"  -> 'Aqua' NOT present in HTML")

        await asyncio.sleep(0.5)


async def main():
    dsn = settings.database_url.replace('postgresql+psycopg://', 'postgresql://')
    conn = await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)

    try:
        for brand in BRANDS:
            await investigate_brand(conn, brand)
    finally:
        await conn.close()
    print("\n\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
