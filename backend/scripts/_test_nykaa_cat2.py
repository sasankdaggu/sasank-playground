"""Test category page URLs and dump categoryListing structure."""
import asyncio, httpx, json, re

PROXY = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def _preloaded_state(html):
    idx = html.find("window.__PRELOADED_STATE__")
    if idx < 0: return {}
    try:
        start = html.index("{", idx)
        end = html.find("</script>", start)
        return json.loads(html[start:end].rstrip("; \n"))
    except: return {}

def show(obj, depth=0, max_depth=3):
    if depth > max_depth: return
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:15]:
            if isinstance(v, (dict, list)) and v:
                print(f"{'  '*depth}{k}: {type(v).__name__}({len(v)})")
                show(v, depth+1, max_depth)
            else:
                print(f"{'  '*depth}{k} = {repr(v)[:100]}")
    elif isinstance(obj, list) and obj:
        for i, item in enumerate(obj[:2]):
            print(f"{'  '*depth}[{i}]:")
            show(item, depth+1, max_depth)
        if len(obj) > 2:
            print(f"{'  '*depth}  ... {len(obj)} total")

URLS = [
    "https://www.nykaa.com/skin/c/8377?brand=Minimalist&page_no=1",
    "https://www.nykaa.com/skin/minimalist/c/8377?brand=Minimalist",
    "https://www.nykaa.com/skin/c/8377?q=Minimalist&sort=popularity",
]

async def test():
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False,
                                  follow_redirects=True,
                                  headers={"User-Agent": UA}) as c:
        for url in URLS:
            for attempt in range(3):
                try:
                    r = await c.get(url)
                    print(f"\n{'='*60}")
                    print(f"URL: {url}")
                    print(f"Status: {r.status_code}, Size: {len(r.text):,}")
                    if r.status_code == 200:
                        state = _preloaded_state(r.text)
                        cl = state.get("categoryListing") or {}
                        print(f"categoryListing keys: {list(cl.keys())[:20]}")
                        # Find the products array
                        for k, v in cl.items():
                            if isinstance(v, list) and v and isinstance(v[0], dict) and v[0].get("slug"):
                                print(f"  Found products at categoryListing.{k} ({len(v)} items)")
                                print(f"  Sample: {v[0].get('name')!r} → {v[0].get('slug')!r}")
                                # Save for deeper inspection
                                with open(f"/tmp/nykaa_cat_{attempt}.html", "w") as f:
                                    f.write(r.text)
                                break
                        break
                    elif r.status_code == 403:
                        print(f"  403 on attempt {attempt+1}, retrying...")
                        await asyncio.sleep(2)
                except Exception as e:
                    print(f"  ERROR: {e}")
                    break
            await asyncio.sleep(1)

asyncio.run(test())
