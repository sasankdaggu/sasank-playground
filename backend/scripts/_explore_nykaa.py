"""Explore Nykaa __NEXT_DATA__ structure for both search and product pages."""
import asyncio, json, re, httpx

PROXY = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def _next_data(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else {}

def _json_ld(html: str) -> list[dict]:
    results = []
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            results.append(json.loads(m.group(1)))
        except Exception:
            pass
    return results

def _print_keys(obj, prefix="", depth=0):
    if depth > 3:
        return
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:20]:
            t = type(v).__name__
            if isinstance(v, (dict, list)):
                print(f"{'  ' * depth}{prefix}{k}: {t}({len(v)})")
                _print_keys(v, "", depth + 1)
            else:
                val = str(v)[:80] if v else None
                print(f"{'  ' * depth}{prefix}{k}: {t} = {val!r}")
    elif isinstance(obj, list) and obj:
        print(f"{'  ' * depth}[0]:")
        _print_keys(obj[0], "", depth + 1)

async def explore():
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False, follow_redirects=True) as c:
        # 1. Product page
        print("\n" + "="*60)
        print("PRODUCT PAGE: __NEXT_DATA__ structure")
        print("="*60)
        r = await c.get(
            "https://www.nykaa.com/minimalist-10percent-niacinamide-face-serum-with-matmarine-zinc-for-reducing-oil-blemishes/p/15022069",
            headers=HEADERS
        )
        nd = _next_data(r.text)
        _print_keys(nd.get("props", {}).get("pageProps", {}))

        print("\n" + "="*60)
        print("PRODUCT PAGE: JSON-LD schemas")
        print("="*60)
        for ld in _json_ld(r.text):
            if isinstance(ld, list):
                for item in ld:
                    t = item.get("@type", "unknown") if isinstance(item, dict) else type(item).__name__
                    print(f"\n--- @type: {t} (from array) ---")
                    if isinstance(item, dict):
                        _print_keys(item)
            else:
                t = ld.get("@type", "unknown")
                print(f"\n--- @type: {t} ---")
                _print_keys(ld)

        # Also dump any window.__STATE__ or similar data blobs
        print("\n" + "="*60)
        print("OTHER DATA SCRIPTS (window.* / __STATE__ etc.)")
        print("="*60)
        for pattern in [r'window\.__STATE__\s*=\s*({.*?});', r'window\.__INITIAL_STATE__\s*=\s*({.*?});']:
            m = re.search(pattern, r.text, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    print(f"Found: {pattern[:30]}")
                    _print_keys(data)
                except Exception as e:
                    print(f"Parse error: {e}")

        # Check for product data in script tags
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.S)
        product_scripts = [s for s in scripts if '"price"' in s and '"name"' in s and len(s) < 50000]
        print(f"\nScripts with price+name: {len(product_scripts)}")
        if product_scripts:
            try:
                data = json.loads(product_scripts[0])
                _print_keys(data)
            except Exception:
                print(product_scripts[0][:500])

        # 2. Brand search page
        print("\n" + "="*60)
        print("BRAND SEARCH: __NEXT_DATA__ structure (q=Minimalist)")
        print("="*60)
        r2 = await c.get(
            "https://www.nykaa.com/search/result/?q=Minimalist&ptype=product&sort=popularity",
            headers=HEADERS
        )
        nd2 = _next_data(r2.text)
        _print_keys(nd2.get("props", {}).get("pageProps", {}))

asyncio.run(explore())
