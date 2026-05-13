"""Test ScraperAPI standard for Nykaa URL discovery."""
import asyncio, httpx, json
from urllib.parse import quote

SCRAPERAPI_KEY = None  # will load from env
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

import os, sys
sys.path.insert(0, ".")
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(".env"), override=True)
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY", "")

def get_products(html):
    idx = html.find("window.__PRELOADED_STATE__")
    if idx < 0: return [], 0
    try:
        start = html.index("{", idx)
        end = html.find("</script>", start)
        state = json.loads(html[start:end].rstrip("; \n"))
        ld = state.get("categoryListing", {}).get("listingData", {})
        products = ld.get("products", [])
        total = ld.get("totalFound", 0)
        return products, total
    except: return [], 0

async def test():
    brand = "Minimalist"
    proxy = f"http://scraperapi:{SCRAPERAPI_KEY}@proxy-server.scraperapi.com:8001"
    urls_to_try = [
        f"https://www.nykaa.com/search/result/?q={quote(brand)}&ptype=product&sort=relevance&category=8377",
        f"https://www.nykaa.com/skin/minimalist/c/8377?brand={quote(brand)}&page_no=1",
        f"https://www.nykaa.com/skin/c/8377?brand={quote(brand)}&page_no=1",
    ]
    async with httpx.AsyncClient(proxy=proxy, timeout=30, verify=False,
                                  follow_redirects=True,
                                  headers={"User-Agent": UA}) as c:
        for url in urls_to_try:
            r = await c.get(url)
            products, total = get_products(r.text)
            print(f"{r.status_code} | {len(r.text):,}b | {len(products)} products | total={total} | {url[:80]}")
            if products:
                print(f"  brands: {set(p.get('brandName') for p in products[:5])}")
                print(f"  sample: {products[0].get('slug')!r}")
            await asyncio.sleep(1)

asyncio.run(test())
