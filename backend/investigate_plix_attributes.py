"""
Check Plix product attributes and descriptionJson for ingredient data.
Check Pilgrim via Shopify CDN JSON endpoint (no rate limit).
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


async def check_plix_attributes(url: str, label: str):
    print(f"\n{'='*60}")
    print(f"PLIX ATTRIBUTES: {label}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text

    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)
    if not m:
        print("  No __NEXT_DATA__")
        return

    obj = json.loads(m.group(1))
    product = obj.get('props', {}).get('pageProps', {}).get('productPageData', {}).get('product', {})

    if not product:
        print("  Product is null")
        return

    # Check attributes
    attributes = product.get('attributes', [])
    print(f"\n  Attributes ({len(attributes)}):")
    for attr in attributes:
        attr_name = attr.get('attribute', {}).get('name', '')
        values = [v.get('name', '') or v.get('value', '') for v in attr.get('values', [])]
        print(f"  - {attr_name}: {str(values)[:200]}")

    # Check descriptionJson
    desc_json = product.get('descriptionJson', '')
    if desc_json:
        try:
            desc_obj = json.loads(desc_json)
            desc_str = json.dumps(desc_obj)
        except Exception:
            desc_str = desc_json
        print(f"\n  descriptionJson ({len(desc_str)} chars)")
        ing_idx = desc_str.lower().find('ingredient')
        if ing_idx >= 0:
            print(f"  Has 'ingredient' at pos {ing_idx}: {desc_str[max(0,ing_idx-50):ing_idx+500][:450]}")
        else:
            print(f"  No 'ingredient' in descriptionJson")
            # Show first 300 chars of structure
            print(f"  Sample: {desc_str[:300]}")

    # Check metadata
    metadata = product.get('metadata', [])
    print(f"\n  Metadata ({len(metadata)}):")
    for meta in metadata:
        k = meta.get('key', '')
        v = meta.get('value', '')
        if 'ingredient' in k.lower() or 'composition' in k.lower():
            print(f"  INGREDIENT META: {k} = {v[:300]}")
        else:
            print(f"  - {k}: {str(v)[:100]}")


async def check_shopify_inci(base_url: str, handle: str, brand: str):
    """Use Shopify CDN JSON endpoint which is less rate-limited."""
    url = f"{base_url}/products/{handle}.json"
    print(f"\n{'='*60}")
    print(f"{brand} SHOPIFY JSON: {url}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        print(f"  HTTP {resp.status_code}")
        if resp.status_code != 200:
            return
        pdata = resp.json().get('product', {})

    desc = pdata.get('body_html', '')
    tags = pdata.get('tags', [])
    title = pdata.get('title', '')
    print(f"  Title: {title}")
    print(f"  Tags: {tags[:10]}")
    print(f"  Description HTML ({len(desc)} chars)")

    ing_idx = desc.lower().find('ingredient')
    if ing_idx >= 0:
        print(f"  Has 'ingredient' at pos {ing_idx}:")
        # Strip HTML tags for readability
        snippet = desc[max(0, ing_idx-100):ing_idx+600]
        clean = re.sub(r'<[^>]+>', ' ', snippet)
        clean = re.sub(r'\s+', ' ', clean).strip()
        print(f"  >> {clean[:500]}")
    else:
        print(f"  No 'ingredient' in body_html")
        # Show first 300 chars stripped
        clean_desc = re.sub(r'<[^>]+>', ' ', desc)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        print(f"  Body content: {clean_desc[:300]}")

    # Check INCI patterns
    inci_pat = re.compile(r'(?:aqua|glycerin|phenoxyethanol|cetearyl|allantoin)', re.IGNORECASE)
    if inci_pat.search(desc):
        m = inci_pat.search(desc)
        print(f"  INCI term '{m.group(0)}' found in body_html")
        snippet = desc[max(0,m.start()-100):m.end()+300]
        clean = re.sub(r'<[^>]+>', ' ', snippet)
        print(f"  >> {clean[:400]}")
    else:
        print(f"  No INCI terms in body_html")


async def check_pixi(base_url: str, handle: str):
    """Pixi is also Shopify."""
    await check_shopify_inci(base_url, handle, "Pixi")


async def main():
    # Plix attributes
    await check_plix_attributes(
        "https://www.plixlife.com/product/guava-glow-set/1207/3168",
        "Guava Glow Set (kit)"
    )
    await check_plix_attributes(
        "https://www.plixlife.com/product/energy/",
        "Energy (supplement)"
    )

    # Pilgrim products via JSON endpoint
    await check_shopify_inci(
        "https://discoverpilgrim.com",
        "the-french-collection-pro-eyeshadow-palette",
        "Pilgrim"
    )
    await check_shopify_inci(
        "https://discoverpilgrim.com",
        "daily-glow-trio",
        "Pilgrim"
    )
    await check_shopify_inci(
        "https://discoverpilgrim.com",
        "the-ultimate-24k-gold-skincare-combo",
        "Pilgrim"
    )

    # Plum
    await check_shopify_inci(
        "https://plumgoodness.com",
        "green-tea-pore-cleansing-face-wash-vegan-50-ml",
        "Plum"
    )
    await check_shopify_inci(
        "https://plumgoodness.com",
        "brightening-hydrating-combo-cica-hya-betaine-vegan-mucin-face-essence-rice-water-10-niacinamide-face-serum",
        "Plum"
    )

    # Pixi
    await check_shopify_inci(
        "https://in.pixibeauty.com",
        "retinol-tonic-40ml-2",
        "Pixi"
    )
    await check_shopify_inci(
        "https://in.pixibeauty.com",
        "cream-base-brush",
        "Pixi"
    )
    await check_shopify_inci(
        "https://in.pixibeauty.com",
        "on-the-glow-starter-kit",
        "Pixi"
    )


if __name__ == "__main__":
    asyncio.run(main())
