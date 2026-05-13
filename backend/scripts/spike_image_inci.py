"""
Spike: Test Claude vision (Haiku) on product packaging images for INCI extraction.

Brands targeted: fixderma, brwn, bioderma_in, lets_hyphen, mcaffeine
Strategy:
  1. Query DB for 2 products per brand with status='no_inci_html'
  2. Use Shopify /products/{handle}.json to get all product images (most reliable)
  3. Rank images: prefer those with alt containing 'ingredient/inci', then images
     with 'make_it_special' / generic numbered names (often back-of-pack), then last images
  4. Fall back to HTML scan (img tags near 'ingredient' keyword) if JSON fails
  5. Call Claude Haiku vision API on the best candidate
  6. Validate + report

READ-ONLY: no DB writes.
"""
from __future__ import annotations

import asyncio
import base64
import html as html_module
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import anthropic
import httpx
import psycopg
import psycopg.rows

from app.config import settings
from scraper.ingredient_schema_detector import _looks_like_inci

DB_URL = os.environ.get("DATABASE_URL", settings.database_url).replace(
    "postgresql+psycopg://", "postgresql://"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_IMG_HEADERS = {
    **_HEADERS,
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}

# Brands to test (slug, base_url)
BRANDS = [
    ("fixderma",    "https://www.fixderma.com"),
    ("brwn",        "https://brwn.in"),
    ("bioderma_in", "https://www.bioderma-india.in"),
    ("lets_hyphen", "https://letshyphen.com"),
    ("mcaffeine",   "https://mcaffeine.com"),
]
PRODUCTS_PER_BRAND = 2
MAX_IMAGES_TOTAL = 15


async def fetch_no_inci_products(
    conn: psycopg.AsyncConnection, brand_slug: str, limit: int = 2
) -> list[dict]:
    """Fetch product listing URLs for a brand where status='no_inci_html'."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT p.id, p.canonical_name, rl.listing_url, q.status
            FROM scraping.ingredient_extraction_queue q
            JOIN core.products p ON p.id = q.product_id
            JOIN core.retailer_listings rl ON rl.id = q.listing_id
            JOIN core.retailers r ON r.id = rl.retailer_id
            WHERE r.slug = %s AND q.status = 'no_inci_html'
            ORDER BY q.created_at
            LIMIT %s
            """,
            (brand_slug, limit),
        )
        return await cur.fetchall()


def _extract_handle_from_url(listing_url: str) -> str | None:
    """Extract /products/{handle} path from a Shopify URL."""
    m = re.search(r"/products/([^/?#]+)", listing_url)
    return m.group(1) if m else None


def _score_image(alt: str | None, src: str, position: int, total: int) -> int:
    """Score a product image — higher = more likely to contain INCI.

    Key insight from spike research:
    - Fixderma: "with_back_box" / "with_back" in src = INCI image (packaging back)
    - brwn: last few images (1660012039707.jpg) = INCI label photo
    - mCaffeine: last image = INCI label photo
    - lets_hyphen: last image = INCI label photo
    - Avoid: "make_it_special" = marketing infographic, NOT INCI
    - Avoid: "key_benefit", "how_to_use", "claim", "benefit" = marketing images
    - Avoid: "box view" / "front_box" = shows front of pack, not INCI
    """
    score = 0
    alt_lower = (alt or "").lower()
    src_lower = src.lower().split("?")[0]  # ignore query params for scoring

    # POSITIVE signals
    # Src signals: back-of-box / packaging back
    if re.search(r"back[_-]?box|with[_-]back|back[_-]pack|back[_-]label|packaging[_-]back", src_lower):
        score += 90
    if re.search(r"ingredient|inci|ingred", src_lower):
        score += 80
    if re.search(r"\bback\b", src_lower):
        score += 40
    if re.search(r"reverse|rear", src_lower):
        score += 30

    # Alt text signals: box/rear view of packaging
    if re.search(r"box view|back box|back view|rear|packaging back", alt_lower):
        score += 60
    # Alt text mentions ingredients — but NOT 'key ingredients' (marketing)
    if "ingredient" in alt_lower and "key" not in alt_lower:
        score += 50

    # Numbered filenames at end of gallery (brwn, mcaffeine, lets_hyphen pattern)
    if re.match(r".*[/_](8|9|10|11|12)\.(png|jpg|jpeg|webp)$", src_lower):
        score += 20
    elif re.match(r".*[/_]\d{10,}\.(png|jpg|jpeg|webp)$", src_lower):
        # Long numeric filename (e.g. 1660012039707.jpg) — often product label scan
        score += 15

    # NEGATIVE signals — marketing images, front-of-pack
    if re.search(r"make.it.special|special_feature", src_lower):
        score -= 30
    if re.search(r"key[_-]benefit|benefit|how[_-]to|how_tu|step[_-]\d|front[_-]box|front[_-]label", src_lower):
        score -= 20
    if re.search(r"claim|review|result|certif|badge|comparison|banner", src_lower):
        score -= 10
    if re.search(r"key.ingredient|hero.ingredient|benefit|claim", alt_lower):
        score -= 15

    # General position boost: last image is often INCI (last in gallery)
    if total > 0:
        if position == total:  # last image
            score += 25
        elif position >= total - 1:  # second-to-last
            score += 10
        elif position >= total - 2:  # third-to-last
            score += 5

    return score


async def get_shopify_product_images(listing_url: str) -> list[dict]:
    """Fetch all product images via Shopify product JSON API.

    Returns list of dicts: {src, alt, position}
    """
    handle = _extract_handle_from_url(listing_url)
    if not handle:
        return []

    parsed = urlparse(listing_url)
    json_url = f"{parsed.scheme}://{parsed.netloc}/products/{handle}.json"
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0, follow_redirects=True) as c:
            r = await c.get(json_url)
        if r.status_code != 200:
            return []
        data = r.json()
        images = data.get("product", {}).get("images", [])
        return [
            {"src": img.get("src", ""), "alt": img.get("alt"), "position": img.get("position", i + 1)}
            for i, img in enumerate(images)
            if img.get("src")
        ]
    except Exception:
        return []


def extract_img_urls_from_html(html: str, base_url: str) -> list[dict]:
    """Fallback: scan HTML for img tags near 'ingredient' keyword.

    Also extracts images from Shopify JSON blobs embedded in page HTML.
    Returns list of dicts: {src, alt, score}
    """
    decoded = html_module.unescape(html)
    found: list[dict] = []
    seen: set[str] = set()

    # Strategy 1: Shopify JSON blobs with alt "Ingredients of..."
    # Pattern: {"alt":"Ingredients...","...","src":"//cdn..."}
    json_alt_pat = re.compile(
        r'"alt":"(Ingredients?[^"]*)"[^}]{0,300}"src":"(//[^"\\]+)"',
        re.DOTALL,
    )
    for m in json_alt_pat.finditer(decoded):
        alt = m.group(1)
        src = "https:" + m.group(2).replace("\\/", "/")
        if src not in seen:
            seen.add(src)
            found.append({"src": src, "alt": alt})

    # Strategy 2: <img> tags near 'ingredient' keyword (within 3000 chars)
    ingredient_re = re.compile(r"ingredient", re.IGNORECASE)
    img_re = re.compile(r'<img[^>]+(?:src|data-src)=["\']([^"\']+)["\']', re.IGNORECASE)

    for m in ingredient_re.finditer(html):
        pos = m.start()
        snippet = html[max(0, pos - 3000): pos + 3000]
        for img_m in img_re.finditer(snippet):
            src = img_m.group(1)
            if not src.startswith("http") and not src.startswith("//"):
                continue
            if src.startswith("//"):
                src = "https:" + src
            if src not in seen:
                seen.add(src)
                found.append({"src": src, "alt": None})

    # Strategy 3: any img whose src contains ingredient/inci/back keywords
    src_kw_re = re.compile(r"ingredient|inci|ingred|back-|_back", re.IGNORECASE)
    for img_m in img_re.finditer(html):
        src = img_m.group(1)
        if src_kw_re.search(src) and src not in seen:
            if src.startswith("//"):
                src = "https:" + src
            seen.add(src)
            found.append({"src": src, "alt": None})

    # Normalize + filter
    parsed_base = urlparse(base_url)
    result = []
    for item in found:
        src = item["src"]
        if src.startswith("/"):
            src = f"{parsed_base.scheme}://{parsed_base.netloc}{src}"
        if src.startswith("data:") or src.endswith(".svg"):
            continue
        if any(skip in src.lower() for skip in ["logo", "cart", "nav", "footer", "header", "favicon"]):
            continue
        result.append({"src": src, "alt": item.get("alt")})

    return result[:8]


def rank_images(images: list[dict], total: int) -> list[dict]:
    """Sort images by likelihood of containing INCI — highest score first."""
    scored = []
    for img in images:
        score = _score_image(img.get("alt"), img["src"], img.get("position", 0), total)
        scored.append({**img, "_score": score})
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored


def detect_media_type_from_bytes(img_bytes: bytes, url: str) -> str:
    """Detect actual media type by inspecting magic bytes, not URL extension.

    Shopify CDN often serves WebP for .jpg/.png URLs via content negotiation.
    """
    if img_bytes[:4] == b"RIFF" and img_bytes[8:12] == b"WEBP":
        return "image/webp"
    if img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if img_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if img_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    # Fallback: infer from URL extension
    url_lower = url.lower().split("?")[0]
    if url_lower.endswith(".png"):
        return "image/png"
    if url_lower.endswith(".webp"):
        return "image/webp"
    if url_lower.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


async def fetch_page_html(url: str) -> str:
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=20.0, follow_redirects=True) as c:
            r = await c.get(url)
        if r.status_code == 200:
            return r.text
        print(f"    [HTTP {r.status_code}] {url}")
        return ""
    except Exception as e:
        print(f"    [fetch error] {url}: {e}")
        return ""


async def fetch_image_bytes(url: str) -> bytes | None:
    # Strip query params that restrict dimensions; request full-size
    clean_url = re.sub(r"[?&]width=\d+", "", url)
    clean_url = re.sub(r"[?&]w=\d+", "", clean_url)
    try:
        async with httpx.AsyncClient(headers=_IMG_HEADERS, timeout=15.0, follow_redirects=True) as c:
            r = await c.get(clean_url)
        if r.status_code == 200 and len(r.content) > 2000:
            return r.content
        print(f"    [image HTTP {r.status_code} | {len(r.content)} bytes] {clean_url[:80]}")
        return None
    except Exception as e:
        print(f"    [image fetch error] {clean_url[:80]}: {e}")
        return None


def call_claude_vision(
    client: anthropic.Anthropic, img_b64: str, media_type: str
) -> tuple[str, int, int]:
    """Call Claude Haiku vision. Returns (response_text, input_tokens, output_tokens)."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_b64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Extract the complete ingredient list from this product image. "
                        "Return ONLY the comma-separated INCI ingredient names, nothing else. "
                        "If no ingredient list is visible, return 'NO_INCI'."
                    ),
                },
            ],
        }],
    )
    text = response.content[0].text
    return text, response.usage.input_tokens, response.usage.output_tokens


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Haiku: $0.80/M input, $4/M output."""
    return (input_tokens / 1_000_000 * 0.80) + (output_tokens / 1_000_000 * 4.0)


async def find_best_candidate_images(listing_url: str, base_url: str, html: str) -> list[dict]:
    """Return ranked candidate images for a product, trying Shopify JSON first."""
    # Try Shopify JSON API (gives all images with alt text)
    shopify_images = await get_shopify_product_images(listing_url)
    if shopify_images:
        ranked = rank_images(shopify_images, total=len(shopify_images))
        print(f"  Shopify JSON: {len(shopify_images)} images found")
        for img in ranked[:5]:
            alt_str = f' alt="{img["alt"][:40]}"' if img.get("alt") else ""
            print(f"    [score={img['_score']:3d}] {img['src'][:80]}{alt_str}")
        return ranked[:5]

    # Fallback: HTML scan
    html_images = extract_img_urls_from_html(html, base_url)
    if html_images:
        ranked = rank_images(html_images, total=len(html_images))
        print(f"  HTML scan: {len(html_images)} candidate images found")
        for img in ranked[:5]:
            alt_str = f' alt="{img["alt"][:40]}"' if img.get("alt") else ""
            print(f"    [score={img['_score']:3d}] {img['src'][:80]}{alt_str}")
        return ranked[:5]

    print("  No candidate images found.")
    return []


async def main() -> None:
    print("=" * 70)
    print("SPIKE: Claude Vision INCI extraction from product packaging images")
    print("=" * 70)
    print()

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    async with await psycopg.AsyncConnection.connect(
        DB_URL, row_factory=psycopg.rows.dict_row
    ) as conn:

        total_images_tested = 0
        total_input_tokens = 0
        total_output_tokens = 0
        results: list[dict] = []

        for brand_slug, brand_base_url in BRANDS:
            if total_images_tested >= MAX_IMAGES_TOTAL:
                print(f"\n[LIMIT] Reached {MAX_IMAGES_TOTAL} images — stopping.")
                break

            print(f"\n{'─' * 60}")
            print(f"BRAND: {brand_slug}  ({brand_base_url})")
            print(f"{'─' * 60}")

            products = await fetch_no_inci_products(conn, brand_slug, PRODUCTS_PER_BRAND)
            if not products:
                print(f"  No 'no_inci_html' products found in queue for {brand_slug}.")
                continue

            for prod in products:
                if total_images_tested >= MAX_IMAGES_TOTAL:
                    break

                prod_name = prod["canonical_name"]
                listing_url = prod["listing_url"]
                print(f"\n  Product: {prod_name[:60]}")
                print(f"  URL:     {listing_url}")

                # Fetch HTML (needed for fallback + context)
                html = await fetch_page_html(listing_url)
                if not html:
                    print("  [SKIP] Could not fetch page HTML.")
                    continue

                candidate_imgs = await find_best_candidate_images(listing_url, brand_base_url, html)
                if not candidate_imgs:
                    print("  [SKIP] No candidate images found.")
                    continue

                # Try top candidates — stop as soon as we get a valid INCI or exhaust top-3
                tested_this_product = False
                max_tries_per_product = 3
                tries = 0
                for img_info in candidate_imgs:
                    if total_images_tested >= MAX_IMAGES_TOTAL:
                        break
                    if tries >= max_tries_per_product:
                        break
                    tries += 1

                    img_url = img_info["src"]
                    img_bytes = await fetch_image_bytes(img_url)
                    if not img_bytes:
                        continue

                    media_type = detect_media_type_from_bytes(img_bytes, img_url)
                    img_b64 = base64.standard_b64encode(img_bytes).decode()

                    print(f"\n  Testing: {img_url[:80]}")
                    print(f"  Size: {len(img_bytes):,} bytes | type: {media_type} | score: {img_info.get('_score', 0)}")

                    try:
                        raw_response, in_tok, out_tok = call_claude_vision(client, img_b64, media_type)
                    except anthropic.BadRequestError as e:
                        print(f"  [Claude API error] {e}")
                        continue
                    except Exception as e:
                        print(f"  [Claude API error] {e}")
                        continue

                    total_images_tested += 1
                    total_input_tokens += in_tok
                    total_output_tokens += out_tok
                    cost = estimate_cost(in_tok, out_tok)

                    is_valid = (
                        _looks_like_inci(raw_response)
                        and raw_response.strip() not in ("NO_INCI", "NO_INCI.")
                    )
                    response_preview = raw_response[:200].replace("\n", " ").strip()

                    print(f"  Claude response ({len(raw_response)} chars): {response_preview}")
                    print(f"  Valid INCI: {'YES' if is_valid else 'NO'}")
                    print(f"  Tokens: input={in_tok}, output={out_tok} | Cost: ${cost:.5f}")

                    results.append({
                        "brand": brand_slug,
                        "product": prod_name,
                        "img_url": img_url,
                        "response_preview": response_preview,
                        "valid_inci": is_valid,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "cost_usd": cost,
                        "img_score": img_info.get("_score", 0),
                    })

                    tested_this_product = True
                    if is_valid:
                        break  # success — no need to try more images for this product

                if not tested_this_product:
                    print("  [SKIP] No downloadable image succeeded for this product.")

        # ── Summary ──────────────────────────────────────────────────────────
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Images tested:         {total_images_tested}")
        print(f"Total input tokens:    {total_input_tokens:,}")
        print(f"Total output tokens:   {total_output_tokens:,}")
        total_cost = estimate_cost(total_input_tokens, total_output_tokens)
        print(f"Total cost (this run): ${total_cost:.4f}")
        if total_images_tested:
            avg_cost = total_cost / total_images_tested
            print(f"Avg cost/image:        ${avg_cost:.4f}")

        valid = [r for r in results if r["valid_inci"]]
        invalid = [r for r in results if not r["valid_inci"]]
        print(f"\nValid INCI extractions: {len(valid)} / {len(results)}")

        if valid:
            print("\nSuccessful extractions:")
            for r in valid:
                print(f"  [{r['brand']}] {r['product'][:55]}")
                print(f"    First 150 chars: {r['response_preview'][:150]}")

        if invalid:
            print("\nFailed / NO_INCI:")
            for r in invalid:
                print(f"  [{r['brand']}] {r['product'][:55]}")
                print(f"    Response: {r['response_preview'][:100]}")

        # Cost projection for full runs
        print()
        print("── Cost projection (using avg tokens from this run) ──")
        if total_images_tested:
            avg_in = total_input_tokens / total_images_tested
            avg_out = total_output_tokens / total_images_tested
            avg_cost_per = estimate_cost(avg_in, avg_out)
            counts = [
                ("fixderma",    184),
                ("brwn",         20),
                ("bioderma_in",   7),
                ("mcaffeine",    50),
                ("lets_hyphen",  30),
            ]
            for brand, count in counts:
                proj = avg_cost_per * count
                print(f"  {brand:<15} {count:>4} products → ${proj:.2f}")
            total_proj = avg_cost_per * sum(c for _, c in counts)
            print(f"  {'TOTAL':<15} {sum(c for _, c in counts):>4} products → ${total_proj:.2f}")
            print(f"\n  (avg {avg_in:.0f} input + {avg_out:.0f} output tokens/image @ Haiku pricing)")


if __name__ == "__main__":
    asyncio.run(main())
