"""
Production INCI extractor using Claude Haiku vision on product packaging images.

Brands: fixderma, brwn, mcaffeine, lets_hyphen
Strategy:
  1. Query DB for products with status='no_inci_html'
  2. Use Shopify /products/{handle}.json to get ranked images
  3. Score and pick top 2 candidates
  4. Call Claude Haiku vision, validate extraction quality
  5. Update scraping.ingredient_extraction_queue and core.products on success

Usage:
  .venv/bin/python scripts/run_vision_inci.py                     # all brands
  .venv/bin/python scripts/run_vision_inci.py --brand fixderma    # one brand
  .venv/bin/python scripts/run_vision_inci.py --brand fixderma --dry-run --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import html as html_module
import os
import re
import sys
import time
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

# ── Config ─────────────────────────────────────────────────────────────────────

DB_URL = os.environ.get("DATABASE_URL", settings.database_url).replace(
    "postgresql+psycopg://", "postgresql://"
)

BRANDS = [
    ("fixderma",    "https://www.fixderma.com"),
    ("brwn",        "https://brwn.in"),
    ("mcaffeine",   "https://mcaffeine.com"),
    ("lets_hyphen", "https://letshyphen.com"),
]

# lets_hyphen: skip kits/bundles/combos — only individual products
_SKIP_NAME_PATTERNS = (
    "kit", "combo", "bundle", "set of", "gift", "routine", "essentials",
    "set-of", "pack-of",
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

PROMPT = """Extract the complete ingredient list from this product packaging image.
Return ONLY the comma-separated INCI ingredient names exactly as printed, nothing else.
If no ingredient list is clearly visible, return exactly: NO_INCI"""

# Haiku pricing: $0.80/M input, $4/M output
_COST_PER_M_INPUT = 0.80
_COST_PER_M_OUTPUT = 4.0

# ── Image scoring ──────────────────────────────────────────────────────────────

POSITIVE_SIGNALS = [
    (r"back[_-]?box|with[_-]back|back[_-]pack|back[_-]label|packaging[_-]back", 90),
    (r"ingredient|inci|ingred", 80),
    (r"reverse|rear", 30),
    (r"packaging", 20),
    (r"\bback\b", 40),
    (r"pack", 10),
]

NEGATIVE_SIGNALS = [
    (r"amazon_creativ|amazon.creativ", -100),
    (r"\.gif$", -100),
    (r"whatsapp", -80),
    (r"needhelp", -80),
    (r"\bcreativ\b", -60),
    (r"banner", -50),
    (r"lifestyle", -40),
    (r"model", -30),
    (r"make.it.special|special_feature", -30),
    (r"key[_-]benefit|how[_-]to|how_tu|step[_-]\d|front[_-]box|front[_-]label", -20),
    (r"claim|review|result|certif|badge|comparison", -10),
]


def _score_image(url: str, alt: str, position: int, total: int) -> int:
    """Score an image — higher = more likely to be the INCI label photo."""
    score = 0
    src_lower = url.lower().split("?")[0]
    # Filename only (no path) for pattern matching
    filename = src_lower.rsplit("/", 1)[-1].split("?")[0]
    alt_lower = (alt or "").lower()

    # URL-based positive signals (apply all matching)
    for pattern, bonus in POSITIVE_SIGNALS:
        if re.search(pattern, src_lower):
            score += bonus

    # URL-based negative signals
    for pattern, penalty in NEGATIVE_SIGNALS:
        if re.search(pattern, src_lower):
            score += penalty

    # Long unix timestamp filename = often product label scan (brwn/mcaffeine/lets_hyphen pattern)
    if re.match(r"\d{10,}\.(png|jpg|jpeg|webp)$", filename):
        score += 30

    # Gallery position (8-12) = often back-of-pack for most brands
    if re.match(r".*[/_](8|9|10|11|12)\.(png|jpg|jpeg|webp)$", src_lower):
        score += 20

    # Alt text bonuses
    if "ingredient" in alt_lower:
        score += 100
    if "inci" in alt_lower:
        score += 80
    if re.search(r"box view|back box|back view|rear", alt_lower):
        score += 60
    if "ingredient" in alt_lower and "key" not in alt_lower:
        score += 50  # additional for non-marketing ingredient alt
    if re.search(r"key.ingredient|hero.ingredient|benefit|claim", alt_lower):
        score -= 15

    # Position bonus: last few images in gallery often = label shots
    if total > 0:
        if position >= total - 3:
            score += 20
        if position == total - 1:  # very last
            score += 5

    return score


# ── Extraction validation ──────────────────────────────────────────────────────

_MARKETING_PATTERNS = [
    "what makes", "key ingredient", "how to use", "benefits",
    "% active", "hero ingredient", "star ingredient",
]


def _is_high_confidence_extraction(text: str) -> bool:
    """Return True only if the extraction passes all quality checks."""
    if not text:
        return False
    # Must look like INCI
    if not _looks_like_inci(text):
        return False
    # At least 8 comma-separated ingredients
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 8:
        return False
    # No marketing patterns
    text_lower = text.lower()
    if any(pat in text_lower for pat in _MARKETING_PATTERNS):
        return False
    # Must be substantive
    if len(text) < 50:
        return False
    return True


# ── Media type detection ───────────────────────────────────────────────────────

def detect_media_type(data: bytes) -> str:
    """Detect media type from magic bytes — Shopify CDN serves WebP for .jpg URLs."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"  # fallback


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _extract_handle(listing_url: str) -> str | None:
    m = re.search(r"/products/([^/?#]+)", listing_url)
    return m.group(1) if m else None


async def fetch_shopify_images(listing_url: str) -> list[dict]:
    """Get all product images via Shopify JSON API."""
    handle = _extract_handle(listing_url)
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
            {
                "src": img.get("src", ""),
                "alt": img.get("alt") or "",
                "position": img.get("position", i + 1),
            }
            for i, img in enumerate(images)
            if img.get("src")
        ]
    except Exception as e:
        print(f"    [shopify JSON error] {e}")
        return []


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


def extract_img_urls_from_html(html: str, base_url: str) -> list[dict]:
    """Fallback: extract images from HTML when Shopify JSON is unavailable."""
    decoded = html_module.unescape(html)
    found: list[dict] = []
    seen: set[str] = set()

    # Strategy 1: JSON blobs with ingredient alt text
    json_alt_pat = re.compile(
        r'"alt":"(Ingredients?[^"]*)"[^}]{0,300}"src":"(//[^"\\]+)"',
        re.DOTALL,
    )
    for m in json_alt_pat.finditer(decoded):
        src = "https:" + m.group(2).replace("\\/", "/")
        if src not in seen:
            seen.add(src)
            found.append({"src": src, "alt": m.group(1)})

    # Strategy 2: img tags near "ingredient" keyword
    ingredient_re = re.compile(r"ingredient", re.IGNORECASE)
    img_re = re.compile(r'<img[^>]+(?:src|data-src)=["\']([^"\']+)["\']', re.IGNORECASE)
    for m in ingredient_re.finditer(html):
        snippet = html[max(0, m.start() - 3000): m.start() + 3000]
        for img_m in img_re.finditer(snippet):
            src = img_m.group(1)
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http") and src not in seen:
                seen.add(src)
                found.append({"src": src, "alt": ""})

    # Strategy 3: img src containing back/ingredient keywords
    kw_re = re.compile(r"ingredient|inci|ingred|back[_-]|_back", re.IGNORECASE)
    for img_m in img_re.finditer(html):
        src = img_m.group(1)
        if kw_re.search(src) and src not in seen:
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http"):
                seen.add(src)
                found.append({"src": src, "alt": ""})

    parsed_base = urlparse(base_url)
    result = []
    for i, item in enumerate(found):
        src = item["src"]
        if src.startswith("/"):
            src = f"{parsed_base.scheme}://{parsed_base.netloc}{src}"
        if src.startswith("data:") or src.endswith(".svg"):
            continue
        if any(skip in src.lower() for skip in ["logo", "cart", "nav", "footer", "header", "favicon"]):
            continue
        result.append({"src": src, "alt": item.get("alt", ""), "position": i})
    return result[:10]


async def fetch_image_bytes(url: str) -> bytes | None:
    # Strip dimension query params to get full-size image
    clean_url = re.sub(r"[?&]width=\d+", "", url)
    clean_url = re.sub(r"[?&]w=\d+", "", clean_url)
    clean_url = re.sub(r"[?&]height=\d+", "", clean_url)
    # Clean up trailing & or ?
    clean_url = clean_url.rstrip("?&")
    try:
        async with httpx.AsyncClient(headers=_IMG_HEADERS, timeout=20.0, follow_redirects=True) as c:
            r = await c.get(clean_url)
        if r.status_code == 200 and len(r.content) > 2000:
            return r.content
        print(f"    [image {r.status_code} | {len(r.content)} bytes] {clean_url[:80]}")
        return None
    except Exception as e:
        print(f"    [image error] {clean_url[:80]}: {e}")
        return None


# ── Claude API ─────────────────────────────────────────────────────────────────

def call_claude_vision(
    client: anthropic.Anthropic,
    img_b64: str,
    media_type: str,
) -> tuple[str, int, int]:
    """Call Claude Haiku vision. Returns (text, input_tokens, output_tokens)."""
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
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    text = response.content[0].text.strip()
    return text, response.usage.input_tokens, response.usage.output_tokens


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * _COST_PER_M_INPUT) + (output_tokens / 1_000_000 * _COST_PER_M_OUTPUT)


# ── DB queries ─────────────────────────────────────────────────────────────────

async def fetch_products(
    conn: psycopg.AsyncConnection,
    brand_slug: str,
    limit: int | None,
    skip_kits: bool = False,
) -> list[dict]:
    """Fetch no_inci_html products for a brand."""
    sql = """
        SELECT q.id as queue_id, p.id as product_id, p.canonical_name,
               rl.listing_url, q.status
        FROM scraping.ingredient_extraction_queue q
        JOIN core.products p ON p.id = q.product_id
        JOIN core.retailer_listings rl ON rl.id = q.listing_id
        JOIN core.retailers r ON r.id = rl.retailer_id
        WHERE r.slug = %s AND q.status = 'no_inci_html'
        ORDER BY q.created_at
    """
    params: list = [brand_slug]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    if skip_kits:
        filtered = []
        for row in rows:
            name_lower = (row["canonical_name"] or "").lower()
            if not any(pat in name_lower for pat in _SKIP_NAME_PATTERNS):
                filtered.append(row)
        return filtered
    return rows


async def update_db_success(
    conn: psycopg.AsyncConnection,
    queue_id: int,
    extracted_text: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE scraping.ingredient_extraction_queue
            SET status='done', extracted_text=%s, attempts=attempts+1
            WHERE id=%s
            """,
            (extracted_text, queue_id),
        )
        await cur.execute(
            """
            UPDATE core.products SET ingredients_raw=%s
            WHERE id=(
                SELECT product_id FROM scraping.ingredient_extraction_queue WHERE id=%s
            )
            """,
            (extracted_text, queue_id),
        )
    await conn.commit()


async def update_db_failure(
    conn: psycopg.AsyncConnection,
    queue_id: int,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE scraping.ingredient_extraction_queue
            SET attempts=attempts+1
            WHERE id=%s
            """,
            (queue_id,),
        )
    await conn.commit()


# ── Processing ─────────────────────────────────────────────────────────────────

async def process_brand(
    brand_slug: str,
    brand_base_url: str,
    conn: psycopg.AsyncConnection,
    client: anthropic.Anthropic,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict:
    """Process all no_inci_html products for a brand. Returns summary stats."""
    skip_kits = (brand_slug == "lets_hyphen")
    products = await fetch_products(conn, brand_slug, limit, skip_kits=skip_kits)
    total = len(products)

    if total == 0:
        print(f"  No 'no_inci_html' products found for {brand_slug}.")
        return {"brand": brand_slug, "total": 0, "extracted": 0, "input_tokens": 0, "output_tokens": 0}

    extracted_count = 0
    total_input_tokens = 0
    total_output_tokens = 0
    api_calls = 0

    for idx, prod in enumerate(products, 1):
        prod_name = prod["canonical_name"]
        listing_url = prod["listing_url"]
        queue_id = prod["queue_id"]
        label = f"{brand_slug} [{idx}/{total}] {prod_name[:55]}"

        # Get images — try Shopify JSON first, fallback to HTML scan
        images = await fetch_shopify_images(listing_url)
        source = "shopify_json"
        if not images:
            html = await fetch_page_html(listing_url)
            images = extract_img_urls_from_html(html, brand_base_url)
            source = "html_scan"

        if not images:
            print(f"{label} → no images found")
            await update_db_failure(conn, queue_id, dry_run)
            continue

        # Score and filter candidates
        scored = []
        n = len(images)
        for i, img in enumerate(images):
            score = _score_image(img["src"], img.get("alt", ""), i, n)
            scored.append({**img, "_score": score})
        scored.sort(key=lambda x: x["_score"], reverse=True)

        # Take top 2 candidates with score > -50
        candidates = [img for img in scored[:5] if img["_score"] > -50][:2]

        if not candidates:
            print(f"{label} → no suitable images (all scored ≤ -50)")
            await update_db_failure(conn, queue_id, dry_run)
            continue

        success = False
        for img_info in candidates:
            img_url = img_info["src"]
            img_bytes = await fetch_image_bytes(img_url)
            if not img_bytes:
                continue

            media_type = detect_media_type(img_bytes)
            img_b64 = base64.standard_b64encode(img_bytes).decode()

            # Rate limit: 0.5s sleep between API calls
            if api_calls > 0:
                time.sleep(0.5)

            try:
                raw_text, in_tok, out_tok = call_claude_vision(client, img_b64, media_type)
            except anthropic.BadRequestError as e:
                print(f"    [Claude error] {e}")
                continue
            except Exception as e:
                print(f"    [Claude error] {e}")
                continue

            api_calls += 1
            total_input_tokens += in_tok
            total_output_tokens += out_tok

            # Reject NO_INCI
            if raw_text in ("NO_INCI", "NO_INCI.") or not raw_text:
                continue

            # High-confidence validation
            if _is_high_confidence_extraction(raw_text):
                ingredient_count = len([p for p in raw_text.split(",") if p.strip()])
                print(f"{label} → {ingredient_count} ingredients (score={img_info['_score']}, src={source})")
                await update_db_success(conn, queue_id, raw_text, dry_run)
                extracted_count += 1
                success = True
                break
            else:
                # Log why it failed validation
                parts = [p.strip() for p in raw_text.split(",") if p.strip()]
                reason = "too few ingredients" if len(parts) < 8 else "failed inci/marketing check"
                print(f"    [validation fail] {reason} | preview: {raw_text[:80]}")

        if not success:
            print(f"{label} → no suitable image")
            await update_db_failure(conn, queue_id, dry_run)

    cost = estimate_cost(total_input_tokens, total_output_tokens)
    print(f"\n  {brand_slug}: extracted {extracted_count}/{total} | ${cost:.4f} | {api_calls} API calls")

    return {
        "brand": brand_slug,
        "total": total,
        "extracted": extracted_count,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }


# ── CLI entry point ────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Extract INCI via Claude Haiku vision")
    parser.add_argument("--brand", help="Run one brand only (fixderma|brwn|mcaffeine|lets_hyphen)")
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Max products per brand (for testing)")
    args = parser.parse_args()

    brands_to_run = BRANDS
    if args.brand:
        brands_to_run = [(slug, url) for slug, url in BRANDS if slug == args.brand]
        if not brands_to_run:
            print(f"Unknown brand: {args.brand}. Valid: {[s for s, _ in BRANDS]}")
            sys.exit(1)

    print("=" * 70)
    print("Vision INCI extractor — Claude Haiku")
    if args.dry_run:
        print("DRY RUN — no DB writes")
    if args.limit:
        print(f"LIMIT: {args.limit} products per brand")
    print("=" * 70)

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    all_results = []
    async with await psycopg.AsyncConnection.connect(
        DB_URL, row_factory=psycopg.rows.dict_row
    ) as conn:
        for brand_slug, brand_base_url in brands_to_run:
            print(f"\n{'─' * 60}")
            print(f"BRAND: {brand_slug}  ({brand_base_url})")
            print(f"{'─' * 60}")
            result = await process_brand(
                brand_slug, brand_base_url, conn, client,
                dry_run=args.dry_run, limit=args.limit,
            )
            all_results.append(result)

    # Final summary
    print()
    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    total_extracted = 0
    total_products = 0
    total_in_tok = 0
    total_out_tok = 0
    for r in all_results:
        cost = estimate_cost(r["input_tokens"], r["output_tokens"])
        pct = (r["extracted"] / r["total"] * 100) if r["total"] > 0 else 0
        print(f"  {r['brand']:<15} {r['extracted']:>4}/{r['total']:<4} ({pct:.0f}%)  ${cost:.4f}")
        total_extracted += r["extracted"]
        total_products += r["total"]
        total_in_tok += r["input_tokens"]
        total_out_tok += r["output_tokens"]

    total_cost = estimate_cost(total_in_tok, total_out_tok)
    total_pct = (total_extracted / total_products * 100) if total_products > 0 else 0
    print(f"  {'TOTAL':<15} {total_extracted:>4}/{total_products:<4} ({total_pct:.0f}%)  ${total_cost:.4f}")
    print()
    print(f"  Input tokens:  {total_in_tok:,}")
    print(f"  Output tokens: {total_out_tok:,}")
    print(f"  Total cost:    ${total_cost:.4f}")

    if args.dry_run:
        print("\n  (Dry run — no DB writes were made)")


if __name__ == "__main__":
    asyncio.run(main())
