"""Deep investigation - look at specific HTML structures for failing products."""
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

async def investigate_deyga_single(url: str, name: str):
    """Look closely at a single Deyga product - is it a bundle? No ingredients at all?"""
    html, status = await fetch_url(url)
    print(f"\n--- DEYGA: {name} ---")
    print(f"Status: {status}, HTML: {len(html)} chars")
    if not html:
        return

    # Extract the JSON-LD Product block
    for block in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(block.group(1).strip())
            if isinstance(data, dict) and data.get('@type') == 'Product':
                desc = data.get('description', '') or ''
                print(f"JSON-LD description (full):\n{desc[:1000]}")
                print(f"---")
        except:
            pass

    # Look for ingredients near the page
    ing_contexts = re.findall(r'.{0,50}[Ii]ngredient.{0,200}', html)
    print(f"Ingredient mentions in HTML ({len(ing_contexts)} total, showing first 5):")
    for ctx in ing_contexts[:5]:
        clean = re.sub(r'<[^>]+>', '', ctx).strip()
        if clean:
            print(f"  >> {clean[:200]}")

async def investigate_quench_single(url: str, name: str):
    """Look closely at Quench Botanics pages - specifically 'free' products and duos."""
    html, status = await fetch_url(url)
    print(f"\n--- QUENCH: {name} ---")
    print(f"Status: {status}, HTML: {len(html)} chars")
    if not html:
        return

    # Check JSON-LD types
    for block in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(block.group(1).strip())
            t = data.get('@type', 'unknown') if isinstance(data, dict) else 'array'
            if isinstance(data, dict):
                print(f"JSON-LD @type: {t}")
                if t == 'ProductGroup':
                    variants = data.get('hasVariant', [])
                    print(f"  ProductGroup has {len(variants)} variants")
                    if variants:
                        v = variants[0]
                        print(f"  First variant keys: {list(v.keys())[:10]}")
                        desc = v.get('description', '') or ''
                        print(f"  First variant description: {desc[:300]}")
                elif t == 'Product':
                    desc = data.get('description', '') or ''
                    print(f"  Product description: {desc[:300]}")
        except Exception as e:
            print(f"JSON-LD parse error: {e}")

    # Check for "Complete Ingredient List" patterns
    cil = re.findall(r'[Cc]omplete\s+[Ii]ngredient\s+[Ll]ist.{0,500}', html)
    print(f"'Complete Ingredient List' occurrences: {len(cil)}")
    for c in cil[:3]:
        clean = re.sub(r'<[^>]+>', '', c).strip()
        print(f"  >> {clean[:300]}")

    # Check for any ingredients section
    ing_sections = re.findall(r'(?:ingredient|INGREDIENT).{0,100}', html)
    print(f"Ingredient mentions: {len(ing_sections)}, first few:")
    for s in ing_sections[:3]:
        clean = re.sub(r'<[^>]+>', '', s).strip()
        if len(clean) > 10:
            print(f"  >> {clean[:150]}")

    # Specifically check if this is a "free" giveaway product (might have no INCI)
    if 'free' in url.lower():
        print(f"  NOTE: URL contains 'free' - likely a free/sample product")

    # Check for metafield content
    mf = re.findall(r'<[^>]*metafield[^>]*>(.*?)</', html, re.DOTALL | re.IGNORECASE)
    if mf:
        print(f"Metafield elements ({len(mf)} found):")
        for m in mf[:3]:
            clean = re.sub(r'<[^>]+>', '', m).strip()
            if len(clean) > 5:
                print(f"  >> {clean[:200]}")

async def investigate_barenecessities_single(url: str, name: str):
    """Look at Bare Necessities pages - find what kinds of products they are."""
    html, status = await fetch_url(url)
    print(f"\n--- BARE NECESSITIES: {name} ---")
    print(f"Status: {status}, HTML: {len(html)} chars")
    if not html:
        return

    # Check for <strong>Ingredients:</strong>
    has_strong = bool(re.search(r'<strong>\s*Ingredients\s*:?\s*</strong>', html, re.IGNORECASE))
    print(f"Has <strong>Ingredients:</strong>: {has_strong}")

    # Check ingredient mentions
    ing = re.findall(r'[Ii]ngredient.{0,200}', html)
    print(f"Ingredient mentions: {len(ing)}")
    for i in ing[:3]:
        clean = re.sub(r'<[^>]+>', '', i).strip()
        if len(clean) > 5:
            print(f"  >> {clean[:200]}")

    # Check for tab structure
    tabs = re.findall(r'<li[^>]*class="[^"]*tab[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL | re.IGNORECASE)
    tab_names = [re.sub(r'<[^>]+>', '', t).strip() for t in tabs]
    print(f"Tab names: {[t for t in tab_names if t][:10]}")

    # Check for the product description section
    desc_match = re.search(r'class="[^"]*product[^"]*description[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
    if desc_match:
        desc_text = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
        print(f"Product description text: {desc_text[:300]}")

    # Determine product type from name
    name_lower = name.lower()
    if any(kw in name_lower for kw in ['book', 'course', 'gift card', 'card', 'charge', 'delivery', 'shipping']):
        print(f"  CATEGORY: Non-cosmetic product (book/course/gift/admin)")
    elif any(kw in name_lower for kw in ['straw', 'toothbrush', 'tumbler', 'loofah', 'comb', 'brush']):
        print(f"  CATEGORY: Non-cosmetic tool/accessory")
    elif any(kw in name_lower for kw in ['kit', 'bundle', 'hamper', 'set', 'gift box', 'combo']):
        print(f"  CATEGORY: Bundle/Kit (multiple products)")
    else:
        print(f"  CATEGORY: Possibly cosmetic product")

async def main():
    # === DEYGA - check 5 products including a non-combo and combo ===
    print("\n" + "="*70)
    print("DEYGA DEEP DIVE")
    print("="*70)

    deyga_samples = [
        ("https://deyga.in/products/abc-combo", "ABC Combo"),
        ("https://deyga.in/products/tooth-brush", "Tooth brush"),
        ("https://deyga.in/products/loofah", "Organic Loofah"),
        ("https://deyga.in/products/gift-card", "Gift Card"),
        ("https://deyga.in/products/wooden-comb-large", "Wooden Comb - Large"),
    ]

    for url, name in deyga_samples:
        await investigate_deyga_single(url, name)
        await asyncio.sleep(1)

    # === QUENCH BOTANICS - check different product types ===
    print("\n" + "="*70)
    print("QUENCH BOTANICS DEEP DIVE")
    print("="*70)

    quench_samples = [
        ("https://quenchbotanics.com/products/acne-control-duo", "Acne Control Duo"),
        ("https://quenchbotanics.com/products/birch-please-clarifying-serum-free", "Birch Please Serum (FREE)"),
        ("https://quenchbotanics.com/products/brightening-lip-oil-with-yuzu-vitamin-c-5-ml", "Brightening Lip Oil 5ML"),
        ("https://quenchbotanics.com/products/kk-headband-pink", "KK Headband Pink"),
        ("https://quenchbotanics.com/products/snail-mucin-collagen-boost-mask-pack-of-1", "Snail Mucin Mask Pack of 1"),
    ]

    for url, name in quench_samples:
        await investigate_quench_single(url, name)
        await asyncio.sleep(1)

    # === BARE NECESSITIES - check all categories ===
    print("\n" + "="*70)
    print("BARE NECESSITIES DEEP DIVE")
    print("="*70)

    bn_samples = [
        ("https://barenecessities.in/products/bare-necessities-how-to-live-a-zero-waste-life-book", "Book"),
        ("https://barenecessities.in/products/compostable-bamboo-tooth-brush-zero-waste-eco-friendly", "Bamboo Toothbrush"),
        ("https://barenecessities.in/products/zero-waste-personal-starter-kit", "Zero Waste Personal Care Kit"),
        ("https://barenecessities.in/products/travel-kit-classic", "Zero Waste Travel Kit"),
        ("https://barenecessities.in/products/empower-her-gift-box-sustainable-gifts-for-her-eco-friendly-clean-beauty", "Empower Her Gift Box"),
    ]

    for url, name in bn_samples:
        await investigate_barenecessities_single(url, name)
        await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(main())
