import httpx, asyncio, re

async def test():
    proxy = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
    url = "https://www.nykaa.com/minimalist-10percent-niacinamide-face-serum-with-matmarine-zinc-for-reducing-oil-blemishes/p/15022069"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    async with httpx.AsyncClient(proxy=proxy, timeout=30, verify=False, follow_redirects=True) as c:
        r = await c.get(url, headers=headers)
        print(f"Status: {r.status_code}, Size: {len(r.text):,} bytes")
        if r.status_code == 200:
            m = re.search(r'"name":\s*"([^"]+)"', r.text)
            print(f"Product found: {m.group(1) if m else '(parse manually)'}")
        else:
            print(r.text[:300])

asyncio.run(test())
