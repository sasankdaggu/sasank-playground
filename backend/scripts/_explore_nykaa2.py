"""Dump raw Nykaa response to understand the structure."""
import asyncio, httpx, re

PROXY = "http://smart-qdihefps8kyv:AATdILUeuHd2KivE@proxy.smartproxy.net:3120"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

async def explore():
    async with httpx.AsyncClient(proxy=PROXY, timeout=30, verify=False, follow_redirects=True) as c:
        r = await c.get(
            "https://www.nykaa.com/minimalist-10percent-niacinamide-face-serum-with-matmarine-zinc-for-reducing-oil-blemishes/p/15022069",
            headers=HEADERS
        )
        print(f"Status: {r.status_code}, Content-Type: {r.headers.get('content-type')}")
        print(f"Size: {len(r.text):,} bytes")
        print(f"\nFirst 2000 chars:")
        print(r.text[:2000])
        print("\n...\n")

        # Check script tags
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.S)
        print(f"Total script tags: {len(scripts)}")
        for i, s in enumerate(scripts[:10]):
            print(f"  script[{i}]: {len(s)} chars | preview: {s[:100].strip()!r}")

        # Check for any JSON-like blobs
        print(f"\nContains __NEXT_DATA__: {'__NEXT_DATA__' in r.text}")
        print(f"Contains 'application/ld+json': {'application/ld+json' in r.text}")
        print(f"Contains 'price': {'\"price\"' in r.text}")
        print(f"Contains 'ingredients': {'ingredient' in r.text.lower()}")

        # Save full HTML for inspection
        with open("/tmp/nykaa_product.html", "w") as f:
            f.write(r.text)
        print("\nFull HTML saved to /tmp/nykaa_product.html")

asyncio.run(explore())
