"""
Deep dive: what JSON structure contains INCI for mamaearth/plum/pilgrim,
and what's happening with Plum's script-embedded INCI.
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


async def deep_dive(label: str, url: str):
    print(f"\n{'='*60}")
    print(f"DEEP DIVE: {label}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as client:
        resp = await client.get(url)
        html = resp.text

    # --- Mamaearth / React/Next JSON ---
    print("\n[1] Checking __NEXT_DATA__ / window.__INITIAL_STATE__ for ingredients key...")
    for pat, name in [
        (r'__NEXT_DATA__\s*=\s*(\{.*?\})\s*;?\s*</script>', '__NEXT_DATA__'),
        (r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})', '__INITIAL_STATE__'),
        (r'window\.__STATE__\s*=\s*(\{.*?\})', '__STATE__'),
    ]:
        matches = re.findall(pat, html, re.DOTALL)
        for raw in matches:
            try:
                obj = json.loads(raw)
                dump = json.dumps(obj)
            except Exception:
                dump = raw
            hits = list(re.finditer(r'"ingredient[s]?"', dump, re.IGNORECASE))
            if hits:
                print(f"  Found {len(hits)} 'ingredient' keys in {name}")
                for h in hits[:3]:
                    start = max(0, h.start() - 20)
                    end = min(len(dump), h.end() + 400)
                    print(f"  >> {dump[start:end][:450]}")
                break

    # --- LD+JSON product schema ---
    print("\n[2] Checking ld+json blocks for ingredients...")
    ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    )
    for i, block in enumerate(ld_blocks):
        try:
            obj = json.loads(block)
        except Exception:
            continue
        dump = json.dumps(obj)
        if re.search(r'"ingredient', dump, re.IGNORECASE):
            print(f"  ld+json block {i}: has 'ingredient' key")
            m = re.search(r'"ingredient[s]?":\s*([^\n]{0,400})', dump, re.IGNORECASE)
            if m:
                print(f"  >> {m.group(0)[:400]}")

    # --- Shopify product JSON (window.ShopifyAnalytics or product JSON endpoint) ---
    print("\n[3] Checking Shopify-style product JSON in inline scripts...")
    # Look for product.metafields or product description containing ingredient
    shopify_product = re.findall(
        r'var\s+meta\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL
    )
    for raw in shopify_product[:2]:
        try:
            obj = json.loads(raw)
            dump = json.dumps(obj)
        except Exception:
            dump = raw
        if re.search(r'ingredient', dump, re.IGNORECASE):
            m = re.search(r'ingredient[s"]?[^,{]*', dump, re.IGNORECASE)
            if m:
                print(f"  Shopify meta has ingredient ref: {m.group(0)[:200]}")

    # --- All inline scripts containing INCI terms ---
    print("\n[4] Checking all <script> blocks for INCI terms (Plum pattern)...")
    INCI_PATTERN = re.compile(
        r"(aqua|glycerin|phenoxyethanol|cetearyl|dimethicone|sodium\s+laureth\s+sulfate|cocamidopropyl)",
        re.IGNORECASE
    )
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    for i, sblock in enumerate(script_blocks):
        if INCI_PATTERN.search(sblock):
            m = INCI_PATTERN.search(sblock)
            start = max(0, m.start() - 100)
            end = min(len(sblock), m.end() + 400)
            snippet = sblock[start:end]
            print(f"  Script block {i} (len={len(sblock)}) has INCI:")
            print(f"  >> {snippet[:500]}")
            # Try to determine if it's JSON-like
            if sblock.strip().startswith('{') or '"ingredients"' in sblock:
                print(f"  --> Looks like JSON data")
            elif 'product' in sblock.lower() and 'variants' in sblock.lower():
                print(f"  --> Looks like Shopify product object")
            break

    # --- Check for product.js endpoint hint ---
    print("\n[5] Looking for Shopify product JSON URL hints...")
    js_url_pattern = re.findall(r'href=["\']([^"\']+\.js)["\']', html)
    product_js = [u for u in js_url_pattern if 'product' in u.lower()]
    for u in product_js[:3]:
        print(f"  Product JS URL: {u}")

    # --- Check for any metafield patterns (Shopify metafields with INCI) ---
    print("\n[6] Looking for Shopify metafield INCI patterns...")
    metafield_pats = re.findall(
        r'(?:metafield|meta_field)[^}]{0,500}ingredient[^}]{0,300}',
        html, re.IGNORECASE | re.DOTALL
    )
    for p in metafield_pats[:2]:
        print(f"  Metafield hit: {p[:300]}")

    print("\n[7] Excerpt search — 500 chars around first 'ingredient' in full HTML...")
    idx = html.lower().find("ingredient")
    if idx >= 0:
        start = max(0, idx - 100)
        end = min(len(html), idx + 500)
        print(f"  >> {html[start:end][:600].replace(chr(10), ' ')}")


async def main():
    cases = [
        ("Mamaearth Baby Wash (no static INCI)", "https://mamaearth.in/product/baby-heat-to-toe-wash"),
        ("Plum Face Wash (INCI in script block)", "https://plumgoodness.com/products/green-tea-pore-cleansing-face-wash-vegan-50-ml"),
        ("Pilgrim Eyeshadow (no JSON INCI)", "https://discoverpilgrim.com/products/the-french-collection-pro-eyeshadow-palette"),
        ("Plix Energy (INCI in JSON)", "https://www.plixlife.com/product/energy/"),
    ]
    for label, url in cases:
        await deep_dive(label, url)


if __name__ == "__main__":
    asyncio.run(main())
