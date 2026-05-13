"""
Precise investigation: where exactly is INCI data in the page, and what CSS class/element contains it?
"""
import asyncio
import re
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv(Path(".env"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

INCI_RE = re.compile(
    r"(?:aqua|glycerin|phenoxyethanol|cetearyl\s+alcohol|dimethicone|"
    r"sodium\s+laureth\s+sulfate|cocamidopropyl\s+betaine|"
    r"niacinamide|retinol|tocopherol|panthenol|allantoin|carbomer|"
    r"xanthan\s+gum|salicylic\s+acid|lactic\s+acid)",
    re.IGNORECASE,
)


def find_inci_in_html_context(html: str, label: str):
    """Find all occurrences of INCI terms and their surrounding HTML context."""
    print(f"\n  --- INCI context analysis for {label} ---")
    found = []
    for m in INCI_RE.finditer(html):
        # Look backward for the opening tag / class
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 200)
        snippet = html[start:end]
        # Skip if it's inside a URL / href
        pre_text = html[max(0, m.start()-50):m.start()]
        if re.search(r'href\s*=\s*["\'][^"\']*$', pre_text) or '/products/' in pre_text:
            continue
        # Skip navigation links
        if '<a ' in snippet and '/collections/' in snippet:
            continue
        # Skip if it's just a meta tag or title
        if '<meta ' in snippet[:100] or '<title>' in snippet[:100]:
            continue
        found.append((m.group(0), snippet))

    if not found:
        print("  No meaningful INCI term found outside nav/URLs")
        return False

    # Print first 3 substantive occurrences
    for term, snippet in found[:3]:
        clean = snippet.replace('\n', ' ').replace('\r', '')
        print(f"  Term: '{term}'")
        # Find what HTML element wraps it
        # Look for class or id attributes nearby
        classes = re.findall(r'class=["\']([^"\']{0,80})["\']', snippet)
        ids = re.findall(r'\bid=["\']([^"\']{0,60})["\']', snippet)
        data_attrs = re.findall(r'data-[a-z-]+=["\']([^"\']{0,60})["\']', snippet)
        if classes:
            print(f"  CSS classes: {classes[-3:]}")
        if ids:
            print(f"  IDs: {ids}")
        if data_attrs:
            print(f"  Data attrs: {data_attrs[:3]}")
        print(f"  HTML ctx: {clean[:300]}")
    return True


async def check_mamaearth_product(url: str, label: str):
    """Mamaearth is a React SPA — check what's actually in SSR HTML."""
    print(f"\n{'='*60}")
    print(f"MAMAEARTH: {label}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text

    # Search for product description / ingredient section
    print(f"\n  [A] Checking for mamaearth product detail JSON in <script>...")
    # Mamaearth is Magento2 / custom React - look for productData or similar
    for pat in [
        r'"ingredients"\s*:\s*"([^"]{10,500})"',
        r'"ingredientList"\s*:\s*\[([^\]]{10,500})\]',
        r'Ingredients["\s:]*([A-Z][a-z]+(?:\s*,\s*[A-Za-z\s]+){3,})',  # comma-separated
        r'INGREDIENTS["\s:]*([A-Z][a-z]+(?:\s*,\s*[A-Za-z\s]+){3,})',
    ]:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            print(f"  Pattern '{pat[:50]}' matched: {m.group(0)[:300]}")

    # What does the product description contain?
    desc_matches = re.findall(
        r'(?:product[-_]?description|productDescription)[^>]*>([^<]{50,500})',
        html, re.IGNORECASE
    )
    for d in desc_matches[:2]:
        print(f"  Product desc snippet: {d[:200]}")

    # Look for any visible ingredient list patterns (comma-separated capitalized words)
    cap_list = re.findall(
        r'(?:Aqua|Water)[,\s]+[A-Z][a-z]+(?:[,\s]+[A-Za-z]+){5,}',
        html
    )
    for c in cap_list[:2]:
        print(f"  Capitalized ingredient list: {c[:300]}")

    found = find_inci_in_html_context(html, label)
    if not found:
        print(f"  CONCLUSION: Mamaearth page for '{label}' has NO INCI in static HTML.")
        print(f"  The ingredient list is loaded via client-side JS / API call after page load.")

    # Check if there's a GraphQL or REST API call pattern
    api_patterns = re.findall(r'(api/[^\s"\'<>]{10,80})', html)
    for p in api_patterns[:5]:
        if 'product' in p.lower() or 'ingredient' in p.lower():
            print(f"  API endpoint hint: {p}")


async def check_plum_product(url: str, label: str):
    """Plum is Shopify — INCI may be in metafields or product description."""
    print(f"\n{'='*60}")
    print(f"PLUM: {label}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text

    # Shopify product JSON is accessible at /products/{handle}.js
    handle_match = re.search(r'/products/([a-z0-9-]+)', url)
    handle = handle_match.group(1) if handle_match else None
    base = re.match(r'https?://[^/]+', url).group(0)

    if handle:
        product_json_url = f"{base}/products/{handle}.js"
        print(f"\n  [A] Fetching Shopify product JSON: {product_json_url}")
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as c:
            try:
                r2 = await c.get(product_json_url)
                if r2.status_code == 200:
                    pdata = r2.json()
                    desc = pdata.get("description", "")
                    # Search for ingredient patterns in description
                    ing_idx = desc.lower().find("ingredient")
                    if ing_idx >= 0:
                        print(f"  Product .js description has 'ingredient' at pos {ing_idx}")
                        print(f"  >> {desc[max(0,ing_idx-50):ing_idx+400][:400]}")
                    elif INCI_RE.search(desc):
                        m = INCI_RE.search(desc)
                        print(f"  Product .js description has INCI term '{m.group(0)}'")
                        print(f"  >> {desc[max(0,m.start()-50):m.end()+200][:300]}")
                    else:
                        print(f"  Product .js description: no ingredient/INCI found")
                        print(f"  Description snippet: {desc[:200]}")

                    # Check metafields
                    metafields = pdata.get("metafields", [])
                    print(f"  Metafields count: {len(metafields)}")
                    for mf in metafields[:5]:
                        if 'ingredient' in str(mf).lower():
                            print(f"  Metafield with ingredient: {str(mf)[:200]}")
                else:
                    print(f"  Product .js returned {r2.status_code}")
            except Exception as e:
                print(f"  Error: {e}")

    print(f"\n  [B] Checking inline HTML for INCI near class='ingredient'...")
    # Look for the ingredients section by class
    for pat in [
        r'class=["\'][^"\']*ingredient[^"\']*["\'][^>]*>([^<]{20,600})',
        r'ingredients?-(?:list|content|popup|section)["\'][^>]*>([^<]{20,400})',
        r'data-section=["\']ingredients?["\'][^>]*>([\s\S]{20,400}?)</div>',
    ]:
        matches = re.findall(pat, html, re.IGNORECASE)
        for m in matches[:2]:
            if INCI_RE.search(m):
                print(f"  Pattern '{pat[:50]}' -> INCI content: {m[:300]}")

    find_inci_in_html_context(html, label)


async def check_pilgrim_product(url: str, label: str):
    """Pilgrim is Shopify — check if INCI is in product description or metafields."""
    print(f"\n{'='*60}")
    print(f"PILGRIM: {label}")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text

    handle_match = re.search(r'/products/([a-z0-9-]+)', url)
    handle = handle_match.group(1) if handle_match else None
    base = re.match(r'https?://[^/]+', url).group(0)

    if handle:
        product_json_url = f"{base}/products/{handle}.js"
        print(f"\n  [A] Fetching Shopify product JSON: {product_json_url}")
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as c:
            try:
                r2 = await c.get(product_json_url)
                if r2.status_code == 200:
                    pdata = r2.json()
                    desc = pdata.get("description", "")
                    tags = pdata.get("tags", [])
                    print(f"  Tags: {tags[:10]}")
                    ing_idx = desc.lower().find("ingredient")
                    if ing_idx >= 0:
                        print(f"  Has 'ingredient' in description at pos {ing_idx}")
                        print(f"  >> {desc[max(0,ing_idx-50):ing_idx+500][:500]}")
                    elif INCI_RE.search(desc):
                        m = INCI_RE.search(desc)
                        print(f"  Has INCI term '{m.group(0)}' in description")
                        print(f"  >> {desc[max(0,m.start()-50):m.end()+200][:300]}")
                    else:
                        print(f"  No ingredient/INCI in description.")
                        print(f"  Description: {desc[:300]}")
                else:
                    print(f"  Product .js returned {r2.status_code}")
            except Exception as e:
                print(f"  Error: {e}")

    find_inci_in_html_context(html, label)


async def main():
    await check_mamaearth_product(
        "https://mamaearth.in/product/baby-heat-to-toe-wash",
        "Baby Head to Toe Wash"
    )
    await check_mamaearth_product(
        "https://mamaearth.in/product/rice-face-wash",
        "Rice Face Wash"
    )
    await check_plum_product(
        "https://plumgoodness.com/products/green-tea-pore-cleansing-face-wash-vegan-50-ml",
        "Green Tea Face Wash 50ml"
    )
    await check_pilgrim_product(
        "https://discoverpilgrim.com/products/the-french-collection-pro-eyeshadow-palette",
        "French Collection Eyeshadow"
    )
    await check_pilgrim_product(
        "https://discoverpilgrim.com/products/daily-glow-trio",
        "Daily Glow Trio (combo)"
    )


if __name__ == "__main__":
    asyncio.run(main())
