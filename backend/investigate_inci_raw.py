"""
Raw HTML extraction: look at the actual ingredient section structure
in Plum, Pilgrim, and Plix pages.
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


def extract_around(html: str, pattern: str, window: int = 800, label: str = "") -> None:
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if m:
        start = max(0, m.start() - 100)
        end = min(len(html), m.end() + window)
        print(f"  [{label}] Found at pos {m.start()}, context:")
        snippet = html[start:end].replace('\n', ' ')
        print(f"  {snippet[:900]}")
    else:
        print(f"  [{label}] NOT FOUND")


async def analyze(url: str, brand: str, product: str):
    print(f"\n{'='*70}")
    print(f"{brand} | {product}")
    print(f"URL: {url}")

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as c:
        resp = await c.get(url)
        html = resp.text

    print(f"\nHTTP {resp.status_code}, page size: {len(html)} chars")

    # Check all patterns that could contain INCI
    print("\n-- Ingredient section patterns --")
    extract_around(html, r'ingredients[-_]?(?:list|content|section|detail|popup)', 900, "ingredient-section-class")
    extract_around(html, r'product[-_]?ingredients?', 900, "product-ingredients")
    extract_around(html, r'"ingredient[s]?"\s*:', 600, "json-ingredients-key")
    extract_around(html, r'Ingredients\s*:</?\s*(?:span|div|p|strong|td)', 600, "Ingredients-label")
    extract_around(html, r'INGREDIENTS\s*[:\-]\s*([A-Z])', 600, "INGREDIENTS-allcaps")
    extract_around(html, r'Aqua\s*[,/]\s*[A-Z][a-z]', 600, "Aqua-comma-list")
    extract_around(html, r'Water\s*[,/]\s*[A-Z][a-z]', 600, "Water-comma-list")

    # For Shopify: look for product description block with INCI
    print("\n-- Shopify description block --")
    extract_around(html, r'class=["\'](?:product[-_]?)?description["\']', 600, "description-class")

    # For Mamaearth: React component with product description
    extract_around(html, r'"description"\s*:\s*"([^"]{50,})"', 400, "json-description-field")

    # Check if there's a tab system with an ingredients tab
    extract_around(html, r'tab.*?ingredient|ingredient.*?tab', 600, "ingredient-tab")

    print()


async def main():
    cases = [
        ("https://plumgoodness.com/products/green-tea-pore-cleansing-face-wash-vegan-50-ml", "Plum", "Green Tea Face Wash 50ml"),
        ("https://discoverpilgrim.com/products/the-french-collection-pro-eyeshadow-palette", "Pilgrim", "French Collection Eyeshadow"),
        ("https://discoverpilgrim.com/products/daily-glow-trio", "Pilgrim", "Daily Glow Trio"),
        ("https://www.plixlife.com/product/energy/", "Plix", "Energy"),
        ("https://mamaearth.in/product/rice-face-wash", "Mamaearth", "Rice Face Wash"),
        ("https://mamaearth.in/product/baby-heat-to-toe-wash", "Mamaearth", "Baby Wash"),
    ]
    for url, brand, product in cases:
        await analyze(url, brand, product)


if __name__ == "__main__":
    asyncio.run(main())
