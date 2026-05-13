"""Fetch and inspect categoryListing.listingData structure."""
import asyncio, httpx, json

PROXY = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

async def test():
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False,
                                  follow_redirects=True, headers={"User-Agent": UA}) as c:
        for attempt in range(4):
            r = await c.get("https://www.nykaa.com/skin/c/8377?brand=Minimalist&page_no=1")
            print(f"Attempt {attempt+1}: {r.status_code}, {len(r.text):,} bytes")
            if r.status_code == 200:
                idx = r.text.find("window.__PRELOADED_STATE__")
                start = r.text.index("{", idx)
                end = r.text.find("</script>", start)
                state = json.loads(r.text[start:end].rstrip("; \n"))
                ld = state.get("categoryListing", {}).get("listingData", {})
                print(f"listingData type: {type(ld).__name__}, keys: {list(ld.keys()) if isinstance(ld, dict) else 'list'}")
                if isinstance(ld, dict):
                    for k, v in ld.items():
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            print(f"\nProducts at listingData['{k}'] → {len(v)} items")
                            p = v[0]
                            for fk in ["name","slug","brandName","mrp","offerPrice","id","url","productUrl","imageUrl"]:
                                if fk in p:
                                    print(f"  {fk} = {repr(p[fk])[:80]}")
                            print(f"  all keys: {list(p.keys())}")
                        else:
                            print(f"  {k}: {type(v).__name__} = {repr(v)[:60]}")
                break
            import asyncio as _a
            await _a.sleep(2)

asyncio.run(test())
