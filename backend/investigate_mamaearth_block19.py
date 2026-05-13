"""
Look specifically at Mamaearth's large script block (block 19) and
Plix's __NEXT_DATA__ to understand product data structure.
"""
import asyncio
import json
import re
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv(Path(".env"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


async def check_mamaearth(url: str, label: str):
    print(f"\n{'='*60}")
    print(f"MAMAEARTH: {label}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text

    # Get script block 19 (the large one with 45k chars)
    script_blocks = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)
    for i, sb in enumerate(script_blocks):
        if len(sb) > 10000:
            print(f"\n  Large script block {i} ({len(sb)} chars):")
            try:
                obj = json.loads(sb)
                jstr = json.dumps(obj, ensure_ascii=False)
            except Exception:
                jstr = sb

            # Search for ingredient-related keys
            for pat in [
                r'"ingredient[s]?"',
                r'"full_ingredient[s]?"',
                r'"product_ingredient[s]?"',
                r'"item_ingredient[s]?"',
                r'"description"',
                r'"composition"',
                r'"components?"',
                r'"specification[s]?"',
            ]:
                hits = list(re.finditer(pat, jstr, re.IGNORECASE))
                if hits:
                    print(f"  Key '{pat}' found {len(hits)} times")
                    for h in hits[:2]:
                        print(f"  >> {jstr[h.start():h.start()+400][:380]}")

            # Also look for any INCI terms in this block
            inci_pat = re.compile(
                r'(?:aqua|glycerin|phenoxyethanol|cetearyl|allantoin|panthenol)',
                re.IGNORECASE
            )
            inci_hits = list(inci_pat.finditer(jstr))
            if inci_hits:
                print(f"\n  INCI terms found in this block: {len(inci_hits)}")
                for h in inci_hits[:3]:
                    print(f"  >> {jstr[max(0,h.start()-100):h.end()+200][:350]}")

    # Check what currentProduct contains
    # The fetchedProduct key had no currentProduct:
    # "currentProduct":false — this means the page SSR didn't include product data
    current_product = re.search(r'"currentProduct"\s*:\s*(\{[\s\S]{100,3000}?\})', html)
    if current_product:
        print(f"\n  currentProduct found: {current_product.group(1)[:600]}")
    else:
        print(f"\n  currentProduct is null/false in SSR — product loaded via client-side JS!")
        # Find the actual product fetch call
        product_url_hints = re.findall(r'"(/api/[^"]{5,80})"', html)
        for p in product_url_hints[:10]:
            print(f"  API hint: {p}")


async def check_plix_product_data(url: str, label: str):
    print(f"\n{'='*60}")
    print(f"PLIX: {label}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text

    # Extract __NEXT_DATA__ (the 400k block)
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)
    if not m:
        print("  No __NEXT_DATA__ found")
        return

    try:
        obj = json.loads(m.group(1))
    except Exception as e:
        print(f"  JSON parse error: {e}")
        return

    jstr = json.dumps(obj, ensure_ascii=False)
    print(f"  __NEXT_DATA__ parsed: {len(jstr)} chars")

    # Navigate the structure
    page_props = obj.get('props', {}).get('pageProps', {})
    product_page = page_props.get('productPageData', {})
    product = product_page.get('product', {})

    if product:
        print(f"\n  Product keys: {list(product.keys())[:20]}")
        # Look for ingredient-related keys
        for k, v in product.items():
            if 'ingredient' in k.lower() or 'composition' in k.lower() or 'formula' in k.lower():
                print(f"  Product.{k}: {str(v)[:300]}")

        # Check description
        desc = product.get('description', '')
        if desc:
            ing_idx = desc.lower().find('ingredient')
            if ing_idx >= 0:
                print(f"  Description has 'ingredient': {desc[max(0,ing_idx-50):ing_idx+400][:400]}")

        # Check sections (Plix uses section_1, section_2, etc.)
        sections = {k: v for k, v in product.items() if k.startswith('section_') or k == 'productDetails'}
        for k, v in list(sections.items())[:5]:
            vs = str(v)
            ing_idx = vs.lower().find('ingredient')
            if ing_idx >= 0:
                print(f"  {k} has 'ingredient': {vs[max(0,ing_idx-50):ing_idx+400][:400]}")
    else:
        print(f"  product is null/empty in __NEXT_DATA__")
        print(f"  pageProps keys: {list(page_props.keys())[:15]}")

    # Search entire __NEXT_DATA__ for ingredient keys
    print(f"\n  Searching all 'ingredient' occurrences in __NEXT_DATA__...")
    hits = list(re.finditer(r'"ingredient[s]?"', jstr, re.IGNORECASE))
    print(f"  Found {len(hits)} occurrences")
    for h in hits[:5]:
        print(f"  >> {jstr[h.start():h.start()+500][:450]}")

    # Also look for the actual ingredient list somewhere
    print(f"\n  Searching for Aqua/Water comma-list patterns in __NEXT_DATA__...")
    inci_list = re.search(r'(?:Aqua|Water)\s*,\s*[A-Za-z\s,]+(?:,\s*[A-Za-z\s]+){5,}', jstr)
    if inci_list:
        print(f"  Found: {inci_list.group(0)[:400]}")
    else:
        print(f"  No comma-separated INCI list found in __NEXT_DATA__")
        # Look for any long comma-separated strings (could be minified)
        long_lists = re.findall(r'"[A-Z][a-z]+(?:,\s*[A-Za-z ]+){8,}"', jstr)
        for ll in long_lists[:3]:
            print(f"  Possible list: {ll[:300]}")


async def main():
    await check_mamaearth("https://mamaearth.in/product/baby-heat-to-toe-wash", "Baby Wash")
    await check_mamaearth("https://mamaearth.in/product/rice-face-wash", "Rice Face Wash")
    await check_plix_product_data("https://www.plixlife.com/product/guava-glow-set/1207/3168", "Guava Glow Set")
    await check_plix_product_data("https://www.plixlife.com/product/isabgol-orange-burst-781/781/2191", "Isabgol")


if __name__ == "__main__":
    asyncio.run(main())
