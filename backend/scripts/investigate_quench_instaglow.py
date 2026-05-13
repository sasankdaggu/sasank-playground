"""Check the specific Quench products that have ingredient data but extractor still fails."""
import asyncio
import sys
import re
import json
sys.path.insert(0, '/Users/sdagguba/sasank-playground/backend')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/Users/sdagguba/sasank-playground/backend/.env'))
import httpx

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "document",
}

async def fetch_url(url: str) -> tuple[str, int]:
    try:
        url_safe = url.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        from urllib.parse import quote
        url_safe = quote(url, safe=":/?=&#%@!$&'()*+,;[]")
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url_safe)
            return resp.text, resp.status_code
    except Exception as e:
        return "", str(e)

async def debug_instaglow():
    """Instaglow has 'Complete Ingredient List' but extractor returns None.
    The issue: 'Complete Ingredient List:' appears in HTML but the <p> regex doesn't match."""
    url = "https://quenchbotanics.com/products/instaglow-sheet-mask-with-yuzu-vitamin-c"
    html, status = await fetch_url(url)
    print(f"=== Instaglow Sheet Mask ===")
    print(f"Status: {status}")

    # Check the exact HTML structure around 'Complete Ingredient List'
    m = re.search(r'.{0,200}Complete\s+Ingredient\s+List.{0,500}', html, re.DOTALL | re.IGNORECASE)
    if m:
        chunk = m.group(0)
        print(f"\nHTML context around 'Complete Ingredient List':")
        print(repr(chunk[:600]))

    # Check the paragraph regex specifically
    p_match = re.search(
        r'<p[^>]*>(?:<strong>)?Complete\s+Ingredient\s+List:?(?:</strong>)?\s*(.*?)</p\s*>',
        html, re.DOTALL | re.IGNORECASE,
    )
    print(f"\n<p> regex match: {bool(p_match)}")
    if p_match:
        print(f"  Group 0: {p_match.group(0)[:200]}")

    # Check JSON-LD description
    for block in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(block.group(1).strip())
            if isinstance(data, list):
                data_list = data
                data = next((d for d in data_list if isinstance(d, dict) and d.get('@type') == 'Product'), {})
            if isinstance(data, dict) and data.get('@type') == 'Product':
                desc = data.get('description', '') or ''
                print(f"\nJSON-LD description (full):")
                print(repr(desc[:2000]))

                # Try the current JSON-LD regex
                jm = re.search(r'[Cc]omplete\s+[Ii]ngredient\s+[Ll]ist\s*:\s*(.+)', desc, re.DOTALL)
                print(f"\nJSON-LD 'Complete Ingredient List' match: {bool(jm)}")
                if jm:
                    raw = jm.group(1).strip()
                    stop = re.search(r'\n\n[A-Z]', raw)
                    if stop:
                        raw = raw[:stop.start()]
                    print(f"Extracted: {raw[:200]}")
        except Exception as e:
            print(f"JSON-LD error: {e}")

async def debug_glow_boost():
    """Glow Boost Serum - has Complete Ingredient List HTML but not in JSON-LD."""
    url = "https://quenchbotanics.com/products/glow-boost-serum-with-yuzu-vitamin-c-30-ml"
    html, status = await fetch_url(url)
    print(f"\n=== Glow Boost Serum 30ML ===")
    print(f"Status: {status}")

    # Check JSON-LD structure
    for block in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(block.group(1).strip())
            t = data.get('@type', 'unknown') if isinstance(data, dict) else 'array'
            print(f"JSON-LD @type: {t}")
            if isinstance(data, dict):
                if t == 'Product':
                    desc = data.get('description', '') or ''
                    print(f"Description: {repr(desc[:500])}")
                elif t == 'ProductGroup':
                    variants = data.get('hasVariant', [])
                    print(f"ProductGroup with {len(variants)} variants")
                    for v in variants[:2]:
                        desc = v.get('description', '') or ''
                        print(f"  Variant description: {repr(desc[:300])}")
        except Exception as e:
            print(f"JSON-LD error: {e}")

    # Check HTML
    m = re.search(r'.{0,100}Complete\s+Ingredient\s+List.{0,300}', html, re.DOTALL | re.IGNORECASE)
    if m:
        print(f"\nHTML 'Complete Ingredient List' context: {repr(m.group(0)[:400])}")

    # What does the p tag look like
    p_match = re.search(
        r'<p[^>]*>(?:<strong>)?Complete\s+Ingredient\s+List:?(?:</strong>)?\s*(.*?)</p\s*>',
        html, re.DOTALL | re.IGNORECASE,
    )
    print(f"\n<p> regex match: {bool(p_match)}")

async def debug_anti_shine_p_structure():
    """Anti-shine Moisturizer Mini - has 'Complete Ingredient List' in HTML but <p> regex fails."""
    url = "https://quenchbotanics.com/products/anti-shine-moisturizer-with-matcha-green-tea-anti-oxidants-mini"
    html, status = await fetch_url(url)
    print(f"\n=== Anti-shine Moisturizer Mini ===")
    print(f"Status: {status}")

    # Check the exact <p> structure
    m = re.search(r'.{0,300}Complete\s+Ingredient\s+List.{0,50}', html, re.DOTALL | re.IGNORECASE)
    if m:
        start_idx = html.find(m.group(0)[:50])
        # Look back for the opening <p> tag
        pre = html[max(0, start_idx-500):start_idx+800]
        print(f"\nHTML context (500 chars before and 800 after 'Complete Ingredient List'):")
        print(repr(pre[:1200]))

async def main():
    await debug_instaglow()
    await asyncio.sleep(1)
    await debug_glow_boost()
    await asyncio.sleep(1)
    await debug_anti_shine_p_structure()

if __name__ == '__main__':
    asyncio.run(main())
