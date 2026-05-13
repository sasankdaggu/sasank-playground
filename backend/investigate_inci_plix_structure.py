"""
Final check: look at the actual JSON structure in Plix (which loads fine)
to understand what the extractor sees vs. what it should look for.
Also check Mamaearth's actual product data structure for ingredients.
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


async def analyze_plix(url: str, product: str):
    """Plix is a custom Next.js / React site. Check how product data is embedded."""
    print(f"\n{'='*70}")
    print(f"PLIX deep structure: {product}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text
    print(f"HTTP {resp.status_code}, {len(html)} chars")

    # Look for window.__APOLLO_STATE__ or similar state containers
    for pat, name in [
        (r'window\.__APOLLO_STATE__\s*=\s*(\{[\s\S]*?\})\s*;', '__APOLLO_STATE__'),
        (r'window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\})\s*;', '__PRELOADED_STATE__'),
        (r'__NEXT_DATA__\s*=\s*(\{[\s\S]*?\})\s*</script>', '__NEXT_DATA__'),
        (r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>([\s\S]*?)</script>', '__NEXT_DATA__ script tag'),
    ]:
        matches = re.findall(pat, html, re.DOTALL)
        if matches:
            raw = matches[0]
            try:
                obj = json.loads(raw)
                jstr = json.dumps(obj)
            except Exception:
                jstr = raw
            print(f"\n  Found {name} ({len(jstr)} chars)")
            # Find ingredients key
            ing_matches = list(re.finditer(r'"ingredient[s]?"', jstr, re.IGNORECASE))
            if ing_matches:
                print(f"  Has {len(ing_matches)} 'ingredient' keys")
                for m in ing_matches[:3]:
                    print(f"  >> {jstr[m.start():m.start()+500][:450]}")
            else:
                print(f"  No 'ingredient' key found")
                # Sample first 500 chars
                print(f"  Sample: {jstr[:200]}")

    # Find actual product data in script tags (Plix seems to use window.plix or similar)
    print("\n  Searching all script blocks for product data...")
    script_blocks = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)
    for i, sb in enumerate(script_blocks):
        if '"ingredients"' in sb.lower() and len(sb) > 200:
            print(f"\n  Script block {i} (len={len(sb)}) has 'ingredients':")
            m = re.search(r'"ingredients?"[^}]{0,600}', sb, re.IGNORECASE)
            if m:
                print(f"  >> {m.group(0)[:500]}")

    # Look for the product page data in HTML (Plix custom pages)
    # They use a Shopify-like or custom CMS
    print("\n  Looking for product metafields / ingredient tab content...")
    # Key ingredient sections
    tab_content = re.findall(
        r'(?:Main\s+Ingredients?|Key\s+Ingredients?|Full\s+Ingredients?|Ingredients?\s+List)[^<]{0,10}</?\s*(?:div|span|h\d|p)[^>]*>([^<]{50,600})',
        html, re.IGNORECASE
    )
    for t in tab_content[:3]:
        print(f"  Tab content: {t[:300]}")

    # Look for ingredient section in the page
    for pat in [
        r'Main Ingredients?([\s\S]{0,1000}?)(?:</div>|<div class)',
        r'Full Ingredients?([\s\S]{0,1000}?)(?:</div>|<div class)',
        r'"ingredients"\s*:\s*"([^"]{20,500})"',
        r'"ingredients"\s*:\s*\[([^\]]{20,500})\]',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            print(f"\n  Pattern '{pat[:50]}': {m.group(1 if m.lastindex else 0)[:400]}")


async def analyze_mamaearth_api(url: str, product: str):
    """Mamaearth uses a custom React + Magento API. Find their API endpoint."""
    print(f"\n{'='*70}")
    print(f"MAMAEARTH API structure: {product}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text
    print(f"HTTP {resp.status_code}, {len(html)} chars")

    # Extract all API URLs from inline scripts
    api_calls = re.findall(r'(?:fetch|axios|graphql)[^\n]{0,200}', html)
    for a in api_calls[:5]:
        print(f"  API call: {a[:200]}")

    # Look for REST API base URL
    api_bases = re.findall(r'["\']([^"\']*(?:api|graphql)[^"\']{5,60})["\']', html)
    for a in list(set(api_bases))[:10]:
        if 'ingredient' in a.lower() or 'product' in a.lower():
            print(f"  API endpoint: {a}")

    # Mamaearth uses something like /rest/V1/products/{sku}
    sku_match = re.search(r'"sku"\s*:\s*"([^"]{6,20})"', html)
    if sku_match:
        sku = sku_match.group(1)
        print(f"\n  Found SKU: {sku}")
        # Try the Magento REST endpoint
        base = "https://mamaearth.in"
        api_url = f"{base}/rest/V1/products/{sku}"
        print(f"  Trying Magento REST: {api_url}")
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as c:
            try:
                r2 = await c.get(api_url)
                print(f"  Response: {r2.status_code}")
                if r2.status_code == 200:
                    pdata = r2.json()
                    attrs = {a['attribute_code']: a['value'] for a in pdata.get('custom_attributes', [])}
                    print(f"  Custom attribute keys: {list(attrs.keys())[:20]}")
                    for k in attrs:
                        if 'ingredient' in k.lower():
                            print(f"  INGREDIENT ATTR '{k}': {attrs[k][:300]}")
            except Exception as e:
                print(f"  Error: {e}")

    # Look for ingredient data in inline JSON blobs
    print("\n  Looking for ingredient data in large JSON blobs...")
    # Mamaearth SSR puts product data as window.__INITIAL_DATA__ or similar
    for pat, name in [
        (r'window\.pageData\s*=\s*(\{[\s\S]{100,}\})\s*;', 'window.pageData'),
        (r'window\.productData\s*=\s*(\{[\s\S]{100,}\})\s*;', 'window.productData'),
        (r'"product"\s*:\s*\{([\s\S]{200,2000}?)\}[\s,]', 'product JSON obj'),
    ]:
        matches = re.findall(pat, html, re.DOTALL)
        if matches:
            raw = matches[0]
            ing_m = re.search(r'ingredient', raw, re.IGNORECASE)
            if ing_m:
                print(f"  {name} has 'ingredient': {raw[max(0,ing_m.start()-50):ing_m.start()+300][:350]}")

    # Final: show all script block sizes to understand what data is there
    script_blocks = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)
    print(f"\n  Script blocks: {len(script_blocks)} total")
    for i, sb in enumerate(script_blocks):
        if len(sb) > 500:
            print(f"  Block {i}: {len(sb)} chars, starts: {sb[:80].replace(chr(10),' ')}")


async def main():
    await analyze_plix("https://www.plixlife.com/product/energy/", "Energy")
    await analyze_plix(
        "https://www.plixlife.com/product/guava-glow-set/1207/3168",
        "Guava Glow Set"
    )
    await analyze_mamaearth_api(
        "https://mamaearth.in/product/baby-heat-to-toe-wash",
        "Baby Wash"
    )
    await analyze_mamaearth_api(
        "https://mamaearth.in/product/rice-face-wash",
        "Rice Face Wash"
    )


if __name__ == "__main__":
    asyncio.run(main())
