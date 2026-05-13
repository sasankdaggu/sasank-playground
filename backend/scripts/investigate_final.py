"""Final investigation - confirm patterns and count product categories."""
import asyncio
import sys
import re
import json
sys.path.insert(0, '/Users/sdagguba/sasank-playground/backend')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/Users/sdagguba/sasank-playground/backend/.env'))
import httpx
from app.config import settings
import psycopg
import psycopg.rows

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "document",
}

async def fetch_url(url: str) -> tuple[str, int]:
    try:
        url_safe = url.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        from urllib.parse import quote
        url_safe = quote(url, safe=":/?=&#%@!$&'()*+,;[]")
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url_safe)
            return resp.text, resp.status_code
    except Exception as e:
        return "", str(e)

async def check_quench_ingredient_list_pattern():
    """Check how many of the failed quench products use 'Ingredient List:' vs 'Complete Ingredient List:'"""
    print("\n=== QUENCH: Checking 'Ingredient List:' pattern (not 'Complete Ingredient List:') ===")

    # These products showed "Ingredient List:" in the description
    test_urls = [
        ("Brightening Lip Oil 5ML", "https://quenchbotanics.com/products/brightening-lip-oil-with-yuzu-vitamin-c-5-ml"),
        ("Instaglow Sheet Mask", "https://quenchbotanics.com/products/instaglow-sheet-mask-with-yuzu-vitamin-c"),
        ("Gentle Cleansing Gel 100ML", "https://quenchbotanics.com/products/gentle-cleansing-gel-face-wash-with-birch-juice-enzymes-100-ml"),
        ("Snail Mucin Mask Pack of 1", "https://quenchbotanics.com/products/snail-mucin-collagen-boost-mask-pack-of-1"),
        ("Skin Detox Gel Face Wash", "https://quenchbotanics.com/products/skin-detox-gel-face-wash-with-matcha-green-tea-anti-oxidants-100-ml-1"),
        ("Bubble Sheet Mask", "https://quenchbotanics.com/products/bubble-sheet-mask-with-matcha-green-tea-anti-oxidants-21-ml"),
        ("Brightening Primer 30ML", "https://quenchbotanics.com/products/brightening-primer-with-yuzu-vitamin-c-30-ml"),
        ("Glow Boost Serum 30ML", "https://quenchbotanics.com/products/glow-boost-serum-with-yuzu-vitamin-c-30-ml"),
    ]

    for name, url in test_urls:
        html, status = await fetch_url(url)
        if not html:
            print(f"  {name}: FETCH FAILED ({status})")
            await asyncio.sleep(0.5)
            continue

        # Check for "Complete Ingredient List:" - current extractor pattern
        has_complete = bool(re.search(r'Complete\s+Ingredient\s+List\s*:', html, re.IGNORECASE))

        # Check for just "Ingredient List:" (no "Complete" prefix) - DIFFERENT PATTERN
        has_plain = bool(re.search(r'(?<!Complete\s)\bIngredient\s+List\s*:', html, re.IGNORECASE))

        # Actually look for exact match in JSON-LD description
        json_ld_desc_has_complete = False
        json_ld_desc_has_plain = False
        json_ld_desc_ingredient_list = None

        for block in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(block.group(1).strip())
                if isinstance(data, list):
                    data = next((d for d in data if isinstance(d, dict) and d.get('@type') == 'Product'), {})
                if isinstance(data, dict) and data.get('@type') in ('Product', 'ProductGroup'):
                    desc = data.get('description', '') or ''
                    json_ld_desc_has_complete = bool(re.search(r'Complete\s+Ingredient\s+List\s*:', desc, re.IGNORECASE))
                    json_ld_desc_has_plain = bool(re.search(r'\bIngredient\s+List\s*:', desc, re.IGNORECASE))
                    m = re.search(r'\bIngredient\s+List\s*:\s*(.{20,300})', desc)
                    if m:
                        json_ld_desc_ingredient_list = m.group(1)[:150]
            except:
                pass

        print(f"\n  {name}:")
        print(f"    HTML has 'Complete Ingredient List:': {has_complete}")
        print(f"    HTML has 'Ingredient List:' (plain): {has_plain}")
        print(f"    JSON-LD desc has 'Complete': {json_ld_desc_has_complete}")
        print(f"    JSON-LD desc has plain 'Ingredient List:': {json_ld_desc_has_plain}")
        if json_ld_desc_ingredient_list:
            print(f"    JSON-LD ingredient list: {json_ld_desc_ingredient_list}")

        await asyncio.sleep(0.8)

async def check_quench_non_cosmetic():
    """Check the clearly non-cosmetic quench products."""
    print("\n=== QUENCH: Non-cosmetic / bundle products ===")
    non_cosmetic_urls = [
        ("KK Headband Pink", "https://quenchbotanics.com/products/kk-headband-pink"),
        ("Acne Control Duo", "https://quenchbotanics.com/products/acne-control-duo"),
        ("Night Repair Duo", "https://quenchbotanics.com/products/night-repair-duo"),
        ("Quench Pink Soft Trousseau", "https://quenchbotanics.com/products/quench-pink-soft-trousseau"),
    ]

    for name, url in non_cosmetic_urls:
        html, status = await fetch_url(url)
        if not html:
            print(f"  {name}: FETCH FAILED ({status})")
            await asyncio.sleep(0.5)
            continue

        # Check JSON-LD type
        json_ld_types = []
        for block in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(block.group(1).strip())
                if isinstance(data, dict):
                    json_ld_types.append(data.get('@type', 'unknown'))
            except:
                pass

        has_complete = bool(re.search(r'Complete\s+Ingredient\s+List\s*:', html, re.IGNORECASE))
        has_plain = bool(re.search(r'\bIngredient\s+List\s*:', html, re.IGNORECASE))

        print(f"  {name}: JSON-LD types={json_ld_types}, has_complete={has_complete}, has_plain={has_plain}")
        await asyncio.sleep(0.5)

async def categorize_bn_products():
    """Categorize all Bare Necessities failed products."""
    print("\n=== BARE NECESSITIES: Product categorization ===")

    dsn = settings.database_url.replace('postgresql+psycopg://', 'postgresql://')
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT p.canonical_name, rl.listing_url
                FROM scraping.ingredient_extraction_queue q
                JOIN core.retailer_listings rl ON rl.id = q.listing_id
                JOIN core.products p ON p.id = q.product_id
                JOIN core.retailers r ON r.id = rl.retailer_id
                WHERE r.slug = 'bare_necessities' AND q.status = 'failed'
                ORDER BY p.canonical_name
                """
            )
            rows = await cur.fetchall()

    non_cosmetic_keywords = ['book', 'course', 'gift card', 'gift cards', 'card', 'charge', 'delivery', 'shipping']
    tool_keywords = ['straw', 'toothbrush', 'tooth brush', 'tumbler', 'loofah', 'comb', 'brush', 'steel cup']
    bundle_keywords = ['kit', 'bundle', 'hamper', 'gift box', 'combo', 'set', 'trousseau', 'gift basket']

    categories = {
        'non_cosmetic_admin': [],
        'non_cosmetic_tool': [],
        'bundle_gift': [],
        'possibly_cosmetic': [],
    }

    for row in rows:
        name = row['canonical_name'].lower()
        if any(kw in name for kw in non_cosmetic_keywords):
            categories['non_cosmetic_admin'].append(row['canonical_name'])
        elif any(kw in name for kw in tool_keywords):
            categories['non_cosmetic_tool'].append(row['canonical_name'])
        elif any(kw in name for kw in bundle_keywords):
            categories['bundle_gift'].append(row['canonical_name'])
        else:
            categories['possibly_cosmetic'].append(row['canonical_name'])

    for cat, items in categories.items():
        print(f"\n  {cat} ({len(items)} products):")
        for item in items:
            print(f"    - {item}")

async def check_deyga_categories():
    """Categorize all Deyga failed products."""
    print("\n=== DEYGA: Product categorization ===")

    combo_keywords = ['combo', 'kit', 'bundle', 'gift', 'set', 'pack']
    tool_keywords = ['comb', 'toothbrush', 'tooth brush', 'loofah', 'brush']
    non_cosmetic_keywords = ['gift card', 'gift-card']

    deyga_products = [
        "ABC Combo", "Acne Relief Combo", "Acne Vanishing Combo", "Best Selling Combo",
        "Bestseller's Gift Set", "Clear Skin Combo", "Daily Essentials Combo",
        "Daily Use Healthy Hair Combo", "Daily Use Healthy Hair Combo (Travel minis)",
        "De-Tan & Anti-Pigmentation Combo", "Deyga New Age Pads - Trial Pack",
        "Double Hydration Combo", "Essentials Gift Set", "Game Changer Combo",
        "Gift Box", "Hair Nourishment combo", "Hair Strengthening Combo",
        "Happy Birthday - Gift Card", "Healthy Glow Combo", "Hydro Boosting Combo",
        "Instant Hair Removal Combo", "Kids Tooth brush", "Mini Foot Spa Combo",
        "Mr. & Mrs. - Gift Card", "Nourished Lips Combo", "Organic Loofah",
        "Sensitive Skin Combo", "Soft Lip Combo", "Tooth brush",
        "Treat Yourself - Gift Card", "Vitamin C Daily Glow Combo",
        "Wheat Straw Toothbrush", "With Love - Gift Card", "Wooden Comb - Large",
        "Wooden Comb - Medium", "Wooden Comb - Small", "🎁 Deyga New Age Pads - Trial Pack"
    ]

    categories = {
        'combo_bundle_kit': [],
        'non_cosmetic_tool': [],
        'non_cosmetic_admin': [],
        'other': [],
    }

    for name in deyga_products:
        name_lower = name.lower()
        if any(kw in name_lower for kw in ['gift card', 'gift-card']):
            categories['non_cosmetic_admin'].append(name)
        elif any(kw in name_lower for kw in ['comb', 'toothbrush', 'tooth brush', 'loofah']):
            categories['non_cosmetic_tool'].append(name)
        elif any(kw in name_lower for kw in ['combo', 'gift', 'kit', 'bundle', 'set', 'pack', 'spa', 'trial']):
            categories['combo_bundle_kit'].append(name)
        else:
            categories['other'].append(name)

    for cat, items in categories.items():
        print(f"\n  {cat} ({len(items)} products):")
        for item in items:
            print(f"    - {item}")

async def main():
    await check_quench_ingredient_list_pattern()
    await check_quench_non_cosmetic()
    await categorize_bn_products()
    await check_deyga_categories()

if __name__ == '__main__':
    asyncio.run(main())
