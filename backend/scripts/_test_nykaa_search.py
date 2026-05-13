"""Test different Nykaa search endpoints to find one that works."""
import asyncio, httpx, json

PROXY = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

URLS_TO_TRY = [
    "https://www.nykaa.com/api/2.0/search?q=Minimalist&ptype=product&sort=popularity&limit=5&page=1",
    "https://www.nykaa.com/sp/search?q=Minimalist&ptype=product&sort=popularity&limit=5",
    "https://www.nykaa.com/search/result/?q=Minimalist&ptype=product&sort=popularity",
    "https://www.nykaa.com/minimalist/brand/4028/category/all",
    "https://www.nykaa.com/skin/minimalist/c/8377?brand=Minimalist",
]

async def test():
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False,
                                  follow_redirects=True,
                                  headers={"User-Agent": UA}) as c:
        for url in URLS_TO_TRY:
            try:
                r = await c.get(url)
                content_type = r.headers.get("content-type", "")
                print(f"{r.status_code} | {len(r.text):>8,}b | {content_type[:40]} | {url}")
                if r.status_code == 200 and ("json" in content_type or r.text.strip().startswith("{")):
                    try:
                        data = r.json()
                        print(f"  JSON keys: {list(data.keys())[:10]}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"ERROR | {url} | {e}")
            await asyncio.sleep(0.5)

asyncio.run(test())
