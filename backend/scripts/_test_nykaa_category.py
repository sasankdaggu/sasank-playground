"""Explore the Nykaa skin category page filtered by brand."""
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
        for k, v in list(obj.items())[:20]:
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
            print(f"{'  '*depth}... ({len(obj)} total items)")

async def test():
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False,
                                  follow_redirects=True,
                                  headers={"User-Agent": UA}) as c:
        r = await c.get("https://www.nykaa.com/skin/minimalist/c/8377?brand=Minimalist")
        print(f"Status: {r.status_code}, Size: {len(r.text):,}")
        state = _preloaded_state(r.text)
        print("\nTop-level state keys:", list(state.keys()))

        # Check categoryListing
        print("\n=== categoryListing ===")
        show(state.get("categoryListing", {}), max_depth=3)

        # Check searchListingPage
        print("\n=== searchListingPage (top keys) ===")
        show(state.get("searchListingPage", {}), max_depth=2)

asyncio.run(test())
