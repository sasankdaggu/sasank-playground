"""Explore window.__PRELOADED_STATE__ and JSON-LD from Nykaa product page."""
import asyncio, json, re, httpx

PROXY = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def _print_keys(obj, depth=0):
    if depth > 4: return
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:30]:
            if isinstance(v, (dict, list)):
                print(f"{'  '*depth}{k}: {type(v).__name__}({len(v)})")
                _print_keys(v, depth + 1)
            else:
                val = repr(v)[:100]
                print(f"{'  '*depth}{k} = {val}")
    elif isinstance(obj, list) and obj:
        _print_keys(obj[0], depth)

async def explore():
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False, follow_redirects=True) as c:
        r = await c.get(
            "https://www.nykaa.com/minimalist-10percent-niacinamide-face-serum-with-matmarine-zinc-for-reducing-oil-blemishes/p/15022069",
            headers=HEADERS
        )

        # 1. Parse __PRELOADED_STATE__
        m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});\s*(?:window|</script>)', r.text, re.S)
        if m:
            state = json.loads(m.group(1))
            print("=== __PRELOADED_STATE__ top-level keys ===")
            for k, v in state.items():
                print(f"  {k}: {type(v).__name__}({len(v) if isinstance(v, (dict, list)) else ''})")

            # Find the product reducer
            for reducer_key in ["productReducer", "pdpReducer", "productDetailReducer", "product"]:
                if reducer_key in state:
                    print(f"\n=== {reducer_key} structure ===")
                    _print_keys(state[reducer_key])
                    break
        else:
            print("No __PRELOADED_STATE__ found")
            # Try raw regex
            m2 = re.search(r'window\.__PRELOADED_STATE__\s*=\s*', r.text)
            if m2:
                print("Found assignment at:", m2.start())
                print("Context:", r.text[m2.start():m2.start()+200])

        # 2. Parse all JSON-LD (plain script tags)
        print("\n=== All JSON-LD scripts ===")
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.S)
        for i, s in enumerate(scripts):
            if '"@type"' in s and '"@context"' in s:
                try:
                    data = json.loads(s)
                    if isinstance(data, list):
                        for item in data:
                            print(f"\nscript[{i}] @type={item.get('@type')}:")
                            _print_keys(item, 1)
                    else:
                        print(f"\nscript[{i}] @type={data.get('@type')}:")
                        _print_keys(data, 1)
                except Exception as e:
                    print(f"script[{i}] parse error: {e}")

        # 3. Check application/ld+json
        print("\n=== application/ld+json scripts ===")
        for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', r.text, re.S):
            try:
                data = json.loads(m.group(1))
                t = data.get("@type") if isinstance(data, dict) else [d.get("@type") for d in data]
                print(f"@type={t}")
                _print_keys(data if isinstance(data, dict) else data[0], 1)
            except Exception as e:
                print(f"parse error: {e}")

asyncio.run(explore())
