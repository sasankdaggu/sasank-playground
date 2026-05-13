"""
Investigate why products have no_inci_html status for specific brands.
For each brand, fetch 3 sample URLs and analyze HTML for ingredient presence.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv(Path(".env"))
from app.config import settings

DSN = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

BRANDS = ["himalaya", "lotus", "fixderma", "mcaffeine", "kama_ayurveda"]

INCI_INDICATORS = [
    r"aqua", r"glycerin", r"niacinamide", r"retinol", r"hyaluronic",
    r"tocopherol", r"panthenol", r"salicylic", r"cetearyl", r"dimethicone",
    r"phenoxyethanol", r"sodium\s+hyaluronate", r"carbomer", r"xanthan",
    r"allantoin", r"lactic\s+acid", r"citric\s+acid",
]
INCI_PATTERN = re.compile("|".join(INCI_INDICATORS), re.IGNORECASE)

INGREDIENT_KEYWORD = re.compile(r"ingredient", re.IGNORECASE)

NON_SKINCARE = re.compile(
    r"\b(gift\s*set|bundle|kit|hamper|combo|accessories?|tool|brush|sponge|towel|bag|pouch)\b",
    re.IGNORECASE,
)


def fetch_samples(brand: str) -> list[tuple[str, str]]:
    query = """
        SELECT rl.listing_url, p.canonical_name
        FROM scraping.ingredient_extraction_queue q
        JOIN core.retailer_listings rl ON rl.id = q.listing_id
        JOIN core.products p ON p.id = q.product_id
        JOIN core.retailers r ON r.id = rl.retailer_id
        WHERE r.slug = %s AND q.status = 'no_inci_html'
        ORDER BY RANDOM() LIMIT 3
    """
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (brand,))
            rows = cur.fetchall()
    return [(row[0], row[1]) for row in rows]


def analyze_html(html: str, product_name: str, url: str) -> dict:
    result = {
        "product_name": product_name,
        "url": url,
        "is_gift_set": bool(NON_SKINCARE.search(product_name)),
        "inci_found_static": False,
        "inci_found_json": False,
        "inci_found_script": False,
        "ingredient_keyword_found": False,
        "notes": [],
        "inci_context": [],
    }

    # 1. Check full static HTML for INCI terms
    inci_matches = list(INCI_PATTERN.finditer(html))
    if inci_matches:
        result["inci_found_static"] = True
        # Grab context around first few matches
        for m in inci_matches[:3]:
            start = max(0, m.start() - 100)
            end = min(len(html), m.end() + 100)
            snippet = html[start:end].strip().replace("\n", " ")
            result["inci_context"].append(f"[static] ...{snippet}...")

    # 2. Check for "ingredient" keyword in static HTML
    ing_matches = list(INGREDIENT_KEYWORD.finditer(html))
    if ing_matches:
        result["ingredient_keyword_found"] = True
        for m in ing_matches[:2]:
            start = max(0, m.start() - 80)
            end = min(len(html), m.end() + 200)
            snippet = html[start:end].strip().replace("\n", " ")
            result["inci_context"].append(f"[ingredient-kw] ...{snippet}...")

    # 3. Check JSON embedded in page (application/json or ld+json or __NEXT_DATA__ etc.)
    json_blocks = re.findall(
        r'<script[^>]*type=["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    # Also look for next/react embedded JSON
    next_data = re.findall(r'__NEXT_DATA__\s*=\s*(\{.*?\})\s*;', html, re.DOTALL)
    all_json = json_blocks + next_data

    for jblock in all_json:
        try:
            obj = json.loads(jblock)
            jstr = json.dumps(obj)
        except Exception:
            jstr = jblock

        if re.search(r'"ingredients?"', jstr, re.IGNORECASE):
            result["inci_found_json"] = True
            # Extract context
            m = re.search(r'"ingredients?":\s*"?([^"}{,\[]{0,300})', jstr, re.IGNORECASE)
            if m:
                result["inci_context"].append(f"[json-ingredients] {m.group(0)[:300]}")
        elif INCI_PATTERN.search(jstr):
            result["inci_found_json"] = True
            m2 = INCI_PATTERN.search(jstr)
            if m2:
                start = max(0, m2.start() - 60)
                end = min(len(jstr), m2.end() + 150)
                result["inci_context"].append(f"[json-inci] ...{jstr[start:end]}...")

    # 4. Check <script> tags for INCI (JS-rendered indicator)
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    for sblock in script_blocks:
        if INCI_PATTERN.search(sblock) and not result["inci_found_json"]:
            result["inci_found_script"] = True
            m = INCI_PATTERN.search(sblock)
            if m:
                start = max(0, m.start() - 60)
                end = min(len(sblock), m.end() + 150)
                result["inci_context"].append(f"[script-inci] ...{sblock[start:end]}...")
            break

    # 5. Extra: Shopify product JSON
    shopify_match = re.search(r'var meta\s*=\s*(\{.*?\});', html, re.DOTALL)
    if shopify_match:
        result["notes"].append("Shopify meta JSON found")

    # 6. Detect if page is mostly empty / JS-gated
    stripped_len = len(re.sub(r'<[^>]+>', '', html))
    if stripped_len < 1000:
        result["notes"].append(f"Thin page — visible text only {stripped_len} chars (likely JS-rendered)")
    else:
        result["notes"].append(f"Page text content: ~{stripped_len} chars")

    return result


async def investigate_brand(brand: str) -> dict:
    print(f"\n{'='*60}")
    print(f"Brand: {brand.upper()}")
    print(f"{'='*60}")

    samples = fetch_samples(brand)
    if not samples:
        print(f"  No no_inci_html products found for brand: {brand}")
        return {"brand": brand, "results": [], "summary": "No samples found"}

    brand_results = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        for url, product_name in samples:
            print(f"\n  Product: {product_name}")
            print(f"  URL:     {url}")
            try:
                resp = await client.get(url)
                html = resp.text
                status = resp.status_code
                print(f"  HTTP:    {status}")
            except Exception as e:
                print(f"  FETCH ERROR: {e}")
                brand_results.append({
                    "product_name": product_name,
                    "url": url,
                    "error": str(e),
                })
                continue

            analysis = analyze_html(html, product_name, url)
            brand_results.append(analysis)

            print(f"  Gift/Bundle: {analysis['is_gift_set']}")
            print(f"  INCI in static HTML: {analysis['inci_found_static']}")
            print(f"  INCI in JSON blocks: {analysis['inci_found_json']}")
            print(f"  INCI in <script>:    {analysis['inci_found_script']}")
            print(f"  'ingredient' keyword: {analysis['ingredient_keyword_found']}")
            for note in analysis["notes"]:
                print(f"  Note: {note}")
            for ctx in analysis["inci_context"][:4]:
                print(f"  Context: {ctx[:250]}")

    # Summarize brand
    print(f"\n  --- SUMMARY for {brand} ---")
    summary = summarize_brand(brand, brand_results)
    print(f"  {summary}")
    return {"brand": brand, "results": brand_results, "summary": summary}


def summarize_brand(brand: str, results: list[dict]) -> str:
    if not results:
        return "No samples fetched."

    valid = [r for r in results if "error" not in r]
    if not valid:
        return "All fetches failed."

    gift_count = sum(1 for r in valid if r.get("is_gift_set"))
    static_inci = sum(1 for r in valid if r.get("inci_found_static"))
    json_inci = sum(1 for r in valid if r.get("inci_found_json"))
    script_inci = sum(1 for r in valid if r.get("inci_found_script"))
    kw_found = sum(1 for r in valid if r.get("ingredient_keyword_found"))
    thin_pages = sum(1 for r in valid if any("Thin page" in n for n in r.get("notes", [])))
    n = len(valid)

    reasons = []
    if gift_count > 0:
        reasons.append(f"{gift_count}/{n} are gift sets/bundles/kits (no INCI expected)")
    if thin_pages > 0:
        reasons.append(f"{thin_pages}/{n} pages are thin/JS-rendered — INCI likely loaded via JS")
    if json_inci > 0:
        reasons.append(f"{json_inci}/{n} have INCI in embedded JSON (extractor may not parse JSON path)")
    if script_inci > 0:
        reasons.append(f"{script_inci}/{n} have INCI hidden in <script> blocks (JS-rendered)")
    if static_inci == n and not reasons:
        reasons.append("INCI IS in static HTML — extraction logic bug suspected")
    if kw_found > 0 and static_inci == 0 and json_inci == 0 and script_inci == 0:
        reasons.append(f"'ingredient' keyword found but no INCI terms — likely key-ingredients / marketing copy only")
    if not reasons:
        reasons.append("Genuinely no INCI on site pages sampled")

    return "; ".join(reasons)


async def main():
    brand_summaries = []
    for brand in BRANDS:
        result = await investigate_brand(brand)
        brand_summaries.append(result)

    print("\n\n" + "="*70)
    print("FINAL SUMMARY — no_inci_html ROOT CAUSES")
    print("="*70)
    for b in brand_summaries:
        print(f"\n{b['brand'].upper()}: {b['summary']}")


if __name__ == "__main__":
    asyncio.run(main())
