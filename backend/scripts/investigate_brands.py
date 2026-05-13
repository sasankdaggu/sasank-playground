"""Investigation script for failed ingredient extractions: deyga, quench_botanics, bare_necessities."""
import asyncio
import sys
import re
import json
sys.path.insert(0, '/Users/sdagguba/sasank-playground/backend')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/Users/sdagguba/sasank-playground/backend/.env'))
import psycopg
import psycopg.rows
import httpx
from app.config import settings

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "document",
}

async def fetch_url(url: str) -> str:
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

def find_inci_patterns(html: str, brand: str) -> dict:
    """Look for various INCI patterns in page HTML."""
    findings = {}

    # Check for JSON-LD
    json_ld_blocks = re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    findings['json_ld_count'] = len(json_ld_blocks)
    findings['json_ld_types'] = []
    for block in json_ld_blocks:
        try:
            data = json.loads(block.strip())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    t = item.get('@type', 'unknown')
                    findings['json_ld_types'].append(t)
                    if t == 'Product':
                        desc = item.get('description', '')
                        findings['json_ld_description_preview'] = desc[:300] if desc else 'EMPTY'
                        findings['has_ingredients_in_description'] = bool(re.search(r'ingredi', desc, re.IGNORECASE))
        except:
            pass

    # Brand-specific checks
    if brand == 'deyga':
        # Check for "Ingredients\n" pattern in JSON-LD description
        for block in json_ld_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    desc = data.get('description', '')
                    m = re.search(r'\bIngredients\b\s*\n([\s\S]+)', desc)
                    findings['deyga_ingredients_section_found'] = bool(m)
                    if m:
                        raw = m.group(1)[:500]
                        findings['deyga_ingredients_raw'] = raw
                        # Check for hyphen-prefixed list
                        findings['deyga_has_hyphen_list'] = bool(re.search(r'^\s*-', raw, re.MULTILINE))
                    # Also check without hyphen list
                    findings['description_has_ingredient_word'] = bool(re.search(r'ingredient', desc, re.IGNORECASE))
            except:
                pass
        # Check for ingredients drawer
        findings['has_ingredients_drawer'] = bool(re.search(r'ingredient.*drawer|drawer.*ingredient', html, re.IGNORECASE))
        findings['has_ingredients_section'] = bool(re.search(r'id=["\']ingredient|class=["\'][^"\']*ingredient', html, re.IGNORECASE))

    elif brand == 'quench_botanics':
        # Check for "Complete Ingredient List" pattern
        m1 = re.search(r'Complete\s+Ingredient\s+List:?\s*(.*?)(?:</p>|<br)', html, re.DOTALL | re.IGNORECASE)
        findings['has_complete_ingredient_list_html'] = bool(m1)
        if m1:
            findings['complete_ingredient_list_preview'] = re.sub(r'<[^>]+>', '', m1.group(0))[:200]

        # Check for metafield div
        findings['has_metafield_div'] = bool(re.search(r'class=["\'][^"\']*metafield[^"\']*["\']', html, re.IGNORECASE))

        # Check for any ingredient mentions
        findings['ingredient_mentions'] = len(re.findall(r'ingredient', html, re.IGNORECASE))

        # Check JSON-LD for Complete ingredient list
        for block in json_ld_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, list):
                    data = next((d for d in data if isinstance(d, dict) and d.get('@type') == 'Product'), {})
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    desc = data.get('description', '')
                    jm = re.search(r'[Cc]omplete\s+[Ii]ngredient\s+[Ll]ist\s*:\s*(.+)', desc, re.DOTALL)
                    findings['json_ld_has_ingredient_list'] = bool(jm)
                    if jm:
                        findings['json_ld_ingredient_list_preview'] = jm.group(1)[:200]
            except:
                pass

    elif brand == 'bare_necessities':
        # Check for <strong>Ingredients:</strong> pattern
        m1 = re.search(r'<strong>\s*Ingredients\s*:?\s*</strong>', html, re.IGNORECASE)
        findings['has_strong_ingredients'] = bool(m1)
        if m1:
            after = html[m1.end(): m1.end() + 500]
            raw = re.sub(r'<[^>]+>', '', after)
            findings['after_strong_ingredients'] = raw[:200]

        # Check for any ingredient-related structure
        findings['ingredient_mentions'] = len(re.findall(r'ingredient', html, re.IGNORECASE))

        # Check for tab structure
        findings['has_tab_structure'] = bool(re.search(r'tab.*content|content.*tab', html, re.IGNORECASE))

        # Check for grouped content
        findings['has_grouped_content'] = bool(re.search(r'grouped.?content|product.?description', html, re.IGNORECASE))

        # Look for any text that could be INCI near ingredients
        ing_match = re.search(r'[Ii]ngredients?\s*[:\-]?\s*([\w\s,\.\(\)-]{50,})', html)
        if ing_match:
            findings['potential_inci_text'] = ing_match.group(1)[:200]

    return findings

async def investigate_brand(conn, brand_slug: str, url_prefix_override: str = None):
    print(f"\n{'='*70}")
    print(f"BRAND: {brand_slug.upper()}")
    print(f"{'='*70}")

    # Get all failed products
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT p.canonical_name, rl.listing_url
            FROM scraping.ingredient_extraction_queue q
            JOIN core.retailer_listings rl ON rl.id = q.listing_id
            JOIN core.products p ON p.id = q.product_id
            JOIN core.retailers r ON r.id = rl.retailer_id
            WHERE r.slug = %s AND q.status = 'failed'
            ORDER BY p.canonical_name
            """,
            (brand_slug,)
        )
        rows = await cur.fetchall()

    print(f"\nTotal failed products: {len(rows)}")
    print("\nALL FAILED PRODUCT NAMES:")
    for i, row in enumerate(rows, 1):
        print(f"  {i:3}. {row['canonical_name']}")
        print(f"       URL: {row['listing_url']}")

    # Get strategy
    domain_pattern = brand_slug.replace('_', '%')
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT brand_domain, css_selector, status, requires_js
            FROM scraping.ingredient_strategies
            WHERE brand_domain ILIKE %s
            """,
            (f'%{domain_pattern}%',)
        )
        strategy_rows = await cur.fetchall()

    print(f"\nSTRATEGY:")
    if strategy_rows:
        for s in strategy_rows:
            print(f"  domain: {s['brand_domain']}")
            print(f"  css_selector: {s['css_selector']}")
            print(f"  status: {s['status']}")
            print(f"  requires_js: {s.get('requires_js', False)}")
    else:
        print("  NO STRATEGY FOUND")

    # Fetch 4-5 failed URLs and check HTML
    sample_urls = [row['listing_url'] for row in rows[:5]]

    print(f"\nHTML ANALYSIS (fetching {len(sample_urls)} URLs):")
    for i, url in enumerate(sample_urls, 1):
        product_name = next(r['canonical_name'] for r in rows if r['listing_url'] == url)
        print(f"\n  [{i}] {product_name}")
        print(f"      URL: {url}")

        html, status_code = await fetch_url(url)
        print(f"      HTTP Status: {status_code}")

        if isinstance(status_code, int) and status_code == 200 and html:
            print(f"      HTML length: {len(html)} chars")
            findings = find_inci_patterns(html, brand_slug)

            for k, v in findings.items():
                if v or v == 0:
                    val_str = str(v)
                    if len(val_str) > 200:
                        val_str = val_str[:200] + '...'
                    print(f"      {k}: {val_str}")
        elif isinstance(status_code, int):
            print(f"      FAILED: HTTP {status_code}")
        else:
            print(f"      FAILED: {status_code}")

        await asyncio.sleep(1)

async def main():
    dsn = settings.database_url.replace('postgresql+psycopg://', 'postgresql://')
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row) as conn:
        await investigate_brand(conn, 'deyga')
        await investigate_brand(conn, 'quench_botanics')
        await investigate_brand(conn, 'bare_necessities')

if __name__ == '__main__':
    asyncio.run(main())
