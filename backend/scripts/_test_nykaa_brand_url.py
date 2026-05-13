"""Test brand-specific Nykaa URLs and check product count + structure."""
import asyncio, httpx, json

PROXY = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

async def fetch_with_retry(c, url, retries=3):
    for i in range(retries):
        try:
            r = await c.get(url)
            if r.status_code == 200:
                return r
            print(f"  attempt {i+1}: {r.status_code}")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"  attempt {i+1} error: {e}")
            await asyncio.sleep(2)
    return None

def get_products(html):
    idx = html.find("window.__PRELOADED_STATE__")
    if idx < 0: return [], {}
    try:
        start = html.index("{", idx)
        end = html.find("</script>", start)
        state = json.loads(html[start:end].rstrip("; \n"))
        ld = state.get("categoryListing", {}).get("listingData", {})
        products = ld.get("products", [])
        meta = {k: ld.get(k) for k in ["totalFound", "count", "categoryName", "brandName"]}
        return products, meta
    except: return [], {}

async def test():
    urls = [
        "https://www.nykaa.com/skin/minimalist/c/8377?brand=Minimalist&page_no=1",
        "https://www.nykaa.com/skin/minimalist/c/8377?brand=Minimalist&page_no=2",
    ]
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False,
                                  follow_redirects=True, headers={"User-Agent": UA}) as c:
        for url in urls:
            print(f"\nURL: {url}")
            r = await fetch_with_retry(c, url)
            if not r:
                print("  FAILED")
                continue
            products, meta = get_products(r.text)
            print(f"  Meta: {meta}")
            print(f"  Products on page: {len(products)}")
            if products:
                brands = set(p.get("brandName","") for p in products)
                print(f"  Brands: {brands}")
                p0 = products[0]
                print(f"  Sample: {p0.get('name')!r}")
                print(f"    slug: {p0.get('slug')!r}")
                print(f"    price: {p0.get('price')} mrp: {p0.get('mrp')}")
            await asyncio.sleep(1)

asyncio.run(test())
