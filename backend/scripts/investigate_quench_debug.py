"""Debug exactly why Quench and Bare Necessities extractors fail."""
import asyncio
import sys
import re
import json
sys.path.insert(0, '/Users/sdagguba/sasank-playground/backend')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/Users/sdagguba/sasank-playground/backend/.env'))
import httpx

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

def run_extractor_deyga(page_html: str) -> str | None:
    """Exact copy of _extract_deyga logic."""
    for block in re.finditer(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
        page_html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1).strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue
        desc = data.get("description") or ""
        m = re.search(r'\bIngredients\b\s*\n([\s\S]+)', desc)
        if not m:
            continue
        raw = m.group(1)
        stop = re.search(r'\n\s*\n[A-Z]', raw)
        if stop:
            raw = raw[:stop.start()]
        items = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith('-'):
                item = line[1:].strip()
                if item:
                    items.append(item)
        if items:
            return ', '.join(items)
        raw = raw.strip()
        return raw if len(raw) > 20 else None
    return None

def run_extractor_quench(page_html: str) -> str | None:
    """Exact copy of _extract_quenchbotanics logic."""
    # Primary: paragraph containing "Complete Ingredient List:" in the page HTML
    m = re.search(
        r'<p[^>]*>(?:<strong>)?Complete\s+Ingredient\s+List:?(?:</strong>)?\s*(.*?)</p\s*>',
        page_html, re.DOTALL | re.IGNORECASE,
    )
    if m:
        raw = re.sub(r'<[^>]+>', '', m.group(0))
        raw = re.sub(r'^Complete\s+Ingredient\s+List:?\s*', '', raw, flags=re.IGNORECASE).strip()
        if len(raw) > 20:
            return raw[:100]
    # Fallback: JSON-LD Product description
    for block in re.finditer(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
        page_html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1).strip())
            if isinstance(data, list):
                data = next((d for d in data if isinstance(d, dict) and d.get('@type') == 'Product'), {})
            if not isinstance(data, dict) or data.get('@type') != 'Product':
                continue
            desc = data.get('description') or ''
            jm = re.search(r'[Cc]omplete\s+[Ii]ngredient\s+[Ll]ist\s*:\s*(.+)', desc, re.DOTALL)
            if jm:
                raw = jm.group(1).strip()
                stop = re.search(r'\n\n[A-Z]', raw)
                if stop:
                    raw = raw[:stop.start()]
                if len(raw) > 20:
                    return raw[:100]
        except Exception:
            pass
    return None

def run_extractor_barenecessities(page_html: str) -> str | None:
    """Exact copy of _extract_barenecessities logic."""
    import html as html_module
    m = re.search(r'<strong>\s*Ingredients\s*:?\s*</strong>', page_html, re.IGNORECASE)
    if not m:
        return None
    after = page_html[m.end(): m.end() + 3_000]
    stop = re.search(r'<(?:strong|div|ul|ol|h[1-6])\b', after, re.IGNORECASE)
    raw = after[:stop.start()] if stop else after[:2_000]
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = html_module.unescape(raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw[:100] if len(raw) > 5 else None

async def debug_quench_anti_shine():
    """Anti-shine moisturizer mini - has 'Complete Ingredient List' but is it a ProductGroup?"""
    url = "https://quenchbotanics.com/products/anti-shine-moisturizer-with-matcha-green-tea-anti-oxidants-mini"
    html, status = await fetch_url(url)
    print(f"\n=== QUENCH: Anti-shine Moisturizer Mini (ProductGroup test) ===")
    print(f"Status: {status}")

    result = run_extractor_quench(html)
    print(f"Extractor result: {result}")

    # Check the full paragraph with ingredients
    m = re.search(r'Complete\s+Ingredient\s+List.{0,2000}', html, re.DOTALL | re.IGNORECASE)
    if m:
        chunk = html[m.start():m.start()+500]
        print(f"\nHTML around 'Complete Ingredient List':")
        print(chunk[:500])

    # Check the <p> tag structure
    p_matches = re.findall(r'<p[^>]*>.*?Complete\s+Ingredient.*?</p\s*>', html, re.DOTALL | re.IGNORECASE)
    print(f"\n<p> tags with 'Complete Ingredient': {len(p_matches)}")
    for p in p_matches[:2]:
        print(f"  {p[:300]}")

async def debug_quench_lip_oil():
    """Brightening Lip Oil 5ML - has description but no ingredient list."""
    url = "https://quenchbotanics.com/products/brightening-lip-oil-with-yuzu-vitamin-c-5-ml"
    html, status = await fetch_url(url)
    print(f"\n=== QUENCH: Brightening Lip Oil 5ML ===")
    print(f"Status: {status}")

    result = run_extractor_quench(html)
    print(f"Extractor result: {result}")

    # What does the page have?
    all_ing = re.findall(r'.{0,30}[Ii]ngredient.{0,100}', html)
    for ctx in all_ing[:10]:
        clean = re.sub(r'<[^>]+>', '', ctx).strip()
        if len(clean) > 10 and 'Product type' not in clean:
            print(f"  >> {clean[:200]}")

async def debug_quench_instaglow():
    """Instaglow Sheet Mask with Yuzu Vitamin C - failed"""
    url = "https://quenchbotanics.com/products/instaglow-sheet-mask-with-yuzu-vitamin-c"
    html, status = await fetch_url(url)
    print(f"\n=== QUENCH: Instaglow Sheet Mask ===")
    print(f"Status: {status}")

    result = run_extractor_quench(html)
    print(f"Extractor result: {result}")

    # Find all ingredient-like content
    all_ing = re.findall(r'.{0,30}[Ii]ngredient.{0,200}', html)
    for ctx in all_ing[:5]:
        clean = re.sub(r'<[^>]+>', '', ctx).strip()
        if len(clean) > 10 and 'Product type' not in clean:
            print(f"  >> {clean[:250]}")

async def debug_quench_gentle_cleanser():
    """Gentle Cleansing Gel - failed, 100ML product"""
    url = "https://quenchbotanics.com/products/gentle-cleansing-gel-face-wash-with-birch-juice-enzymes-100-ml"
    html, status = await fetch_url(url)
    print(f"\n=== QUENCH: Gentle Cleansing Gel 100ML ===")
    print(f"Status: {status}")

    result = run_extractor_quench(html)
    print(f"Extractor result: {result}")

    # Find all ingredient content
    all_ing = re.findall(r'.{0,30}[Ii]ngredient.{0,200}', html)
    for ctx in all_ing[:5]:
        clean = re.sub(r'<[^>]+>', '', ctx).strip()
        if len(clean) > 10 and 'Product type' not in clean:
            print(f"  >> {clean[:250]}")

async def debug_bn_products():
    """Check a few specific BN products with ingredients."""
    print(f"\n=== BARE NECESSITIES: Ingredient-containing products ===")

    # First check a product that DID succeed - to understand the pattern
    from app.config import settings
    import psycopg
    import psycopg.rows
    dsn = settings.database_url.replace('postgresql+psycopg://', 'postgresql://')
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT p.canonical_name, rl.listing_url, q.status
                FROM scraping.ingredient_extraction_queue q
                JOIN core.retailer_listings rl ON rl.id = q.listing_id
                JOIN core.products p ON p.id = q.product_id
                JOIN core.retailers r ON r.id = rl.retailer_id
                WHERE r.slug = 'bare_necessities' AND q.status = 'done'
                ORDER BY p.canonical_name
                LIMIT 5
                """
            )
            done_rows = await cur.fetchall()

    print(f"\nProducts that SUCCEEDED for bare_necessities:")
    for row in done_rows:
        print(f"  - {row['canonical_name']}: {row['listing_url']}")

    # Check one successful product's HTML structure
    if done_rows:
        url = done_rows[0]['listing_url']
        name = done_rows[0]['canonical_name']
        html, status = await fetch_url(url)
        print(f"\nSuccessful product HTML check: {name}")
        print(f"Status: {status}, HTML: {len(html)} chars")
        result = run_extractor_barenecessities(html)
        print(f"Extractor result: {result}")

        # Show the ingredients section context
        m = re.search(r'<strong>\s*Ingredients\s*:?\s*</strong>', html, re.IGNORECASE)
        if m:
            print(f"\nContext around <strong>Ingredients:</strong>:")
            print(html[max(0,m.start()-100):m.end()+500])

async def main():
    await debug_quench_anti_shine()
    await asyncio.sleep(1)
    await debug_quench_lip_oil()
    await asyncio.sleep(1)
    await debug_quench_instaglow()
    await asyncio.sleep(1)
    await debug_quench_gentle_cleanser()
    await asyncio.sleep(1)
    await debug_bn_products()

if __name__ == '__main__':
    asyncio.run(main())
