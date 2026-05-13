"""
Extract INCI ingredient list from a Ponds India product page.

The INCI text is NOT in HTML — it lives only on product images
(back-of-pack / ingredient label shots). This script:
  1. Uses Playwright to fetch the Ponds India product page
  2. Collects all product image URLs
  3. Scores them by how likely they are to show the ingredient label
  4. Downloads the most promising image(s)
  5. Sends each image to Claude Vision and asks it to extract the INCI text
"""

from __future__ import annotations

import base64
import os
import sys
import textwrap
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PRODUCT_URLS_TO_TRY = [
    "https://www.ponds.in/products/super-light-gel",
    "https://www.ponds.in/products/super-light-gel-moisturiser",
    "https://www.ponds.in/products/pond-s-bright-beauty-serum-cream-spf-15-pa-50g",
    "https://www.ponds.in/products/bright-beauty-serum-cream",
    "https://www.ponds.in/products/age-miracle-wrinkle-corrector",
    "https://www.ponds.in/products/pond-s-super-light-gel-oil-free-moisturiser",
]

HOMEPAGE = "https://www.ponds.in"
MAX_IMAGES_TO_ANALYSE = 3          # send at most this many images to Claude
DOWNLOAD_DIR = Path("/tmp/ponds_images")
VISION_MODEL = "claude-opus-4-7"   # or claude-haiku-4-5 for cost

# Keywords that suggest the image shows the back / ingredient panel
INGREDIENT_KEYWORDS = [
    "back", "ingredient", "inci", "label", "pack", "formula",
    "composition", "direction", "usage",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def score_image_url(url: str, alt: str) -> int:
    """Return a priority score — higher is more likely to be the ingredient label."""
    score = 0
    combined = (url + " " + alt).lower()
    for kw in INGREDIENT_KEYWORDS:
        if kw in combined:
            score += 2
    # images that are large variants are more likely to be readable
    if any(x in combined for x in ["_large", "_800", "_1000", "zoom", "hq"]):
        score += 1
    return score


def download_image(url: str, dest: Path) -> Path | None:
    import requests  # available in venv
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        print(f"  Downloaded {len(resp.content):,} bytes -> {dest}")
        return dest
    except Exception as exc:
        print(f"  Download failed for {url}: {exc}")
        return None


def image_to_base64(path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    suffix = path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_type_map.get(suffix, "image/jpeg")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return data, media_type


def ask_claude_for_inci(image_path: Path, client) -> str:
    """Send image to Claude and ask it to extract the INCI ingredient list."""
    import anthropic as _anthropic

    print(f"\n  Sending {image_path.name} to Claude ({VISION_MODEL})...")
    b64, media_type = image_to_base64(image_path)

    prompt = textwrap.dedent("""\
        This image shows the back or label of a skincare product.

        Please carefully examine the image and extract the complete INCI (International
        Nomenclature of Cosmetic Ingredients) ingredient list exactly as printed.

        Return:
        1. The full ingredient list text verbatim (or as close as possible).
        2. A brief note if you cannot clearly read some ingredients due to image quality.

        If this image does NOT show an ingredient list, say so clearly and describe
        what the image actually shows.
    """)

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=VISION_MODEL,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            return next(
                (block.text for block in response.content if block.type == "text"), ""
            )
        except _anthropic.RateLimitError as e:
            wait = 30 * (attempt + 1)
            print(f"  Rate limited (attempt {attempt+1}). Waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            print(f"  Claude API error: {e}")
            return f"[ERROR: {e}]"

    return "[ERROR: rate limit not resolved after retries]"


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def collect_images_from_page(url: str) -> list[dict]:
    """
    Use Playwright to open the page and collect all <img> srcs + alts.
    Returns list of {"url": ..., "alt": ..., "score": ...}
    """
    from playwright.sync_api import sync_playwright

    images: list[dict] = []
    print(f"\nOpening page: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if not resp or resp.status >= 400:
                print(f"  HTTP {resp.status if resp else 'no response'} — skipping.")
                return []
        except Exception as exc:
            print(f"  Navigation error: {exc}")
            return []

        # Give JS a moment to hydrate product images
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(2)

        # Collect all img elements
        img_elements = page.query_selector_all("img")
        print(f"  Found {len(img_elements)} <img> elements on page")

        for el in img_elements:
            src = el.get_attribute("src") or ""
            alt = el.get_attribute("alt") or ""
            data_src = el.get_attribute("data-src") or ""
            srcset = el.get_attribute("srcset") or ""

            # Resolve relative URLs
            for raw_url in [src, data_src]:
                if not raw_url or raw_url.startswith("data:"):
                    continue
                absolute = urljoin(url, raw_url)
                # skip tiny icons / SVGs
                parsed = urlparse(absolute)
                if not parsed.scheme.startswith("http"):
                    continue
                if absolute.endswith(".svg"):
                    continue
                score = score_image_url(absolute, alt)
                images.append({"url": absolute, "alt": alt, "score": score})

            # Also check srcset for higher-res variants
            for part in srcset.split(","):
                part_url = part.strip().split()[0] if part.strip() else ""
                if part_url and not part_url.startswith("data:"):
                    absolute = urljoin(url, part_url)
                    if absolute.endswith(".svg"):
                        continue
                    score = score_image_url(absolute, alt)
                    images.append({"url": absolute, "alt": alt, "score": score})

        # Also try to extract product gallery images via JSON-LD or window.__DATA__
        # Many e-commerce sites embed product images in a JSON blob
        page_html = page.content()
        browser.close()

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[dict] = []
    for img in images:
        if img["url"] not in seen:
            seen.add(img["url"])
            unique.append(img)

    # Sort by score descending
    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique


def find_valid_product_url() -> str | None:
    """Try each candidate URL until one returns a 200."""
    import requests
    for url in PRODUCT_URLS_TO_TRY:
        try:
            r = requests.head(
                url, timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            )
            print(f"  HEAD {url} -> {r.status_code}")
            if r.status_code < 400:
                return url
        except Exception as exc:
            print(f"  HEAD {url} -> error: {exc}")
    return None


def find_product_url_from_homepage() -> str | None:
    """
    Use Playwright to visit the Ponds India homepage and find
    actual product page links (e.g. /products/...).
    """
    from playwright.sync_api import sync_playwright

    print(f"\nScraping homepage for product links: {HOMEPAGE}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        try:
            page.goto(HOMEPAGE, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as exc:
            print(f"  Error loading homepage: {exc}")
            browser.close()
            return None

        # Collect all href links
        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.getAttribute('href'))"
        )
        browser.close()

    from urllib.parse import urljoin
    product_links = []
    for href in links:
        if not href:
            continue
        absolute = urljoin(HOMEPAGE, href)
        # Shopify product pages are at /products/...
        if "/products/" in absolute and absolute.startswith("https://"):
            product_links.append(absolute)

    # Deduplicate
    seen = set()
    unique_products = []
    for link in product_links:
        if link not in seen:
            seen.add(link)
            unique_products.append(link)

    print(f"  Found {len(unique_products)} product links on homepage.")
    for link in unique_products[:10]:
        print(f"    {link}")

    if unique_products:
        return unique_products[0]  # try the first product

    return None


def main() -> None:
    # -- Load API key --
    from dotenv import load_dotenv
    load_dotenv("/Users/sdagguba/sasank-playground/backend/.env")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fall back to app settings
        try:
            sys.path.insert(0, "/Users/sdagguba/sasank-playground/backend")
            from app.config import settings
            api_key = settings.anthropic_api_key
        except Exception:
            pass

    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in .env or app.config")
        sys.exit(1)

    print(f"Anthropic API key loaded: {api_key[:8]}...")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    # -- Find a valid product URL --
    print("\n--- Step 1: Finding valid Ponds India product URL ---")
    product_url = find_valid_product_url()
    if not product_url:
        print("None of the candidate URLs returned 200. Crawling homepage for product links...")
        product_url = find_product_url_from_homepage()
    if not product_url:
        print("Could not find a product URL. Falling back to homepage.")
        product_url = HOMEPAGE
    print(f"Using URL: {product_url}")

    # -- Collect images from the page --
    print("\n--- Step 2: Fetching product page and collecting images ---")
    images = collect_images_from_page(product_url)

    if not images:
        print("No images found. Exiting.")
        sys.exit(1)

    print(f"\nAll images found ({len(images)} unique):")
    for i, img in enumerate(images[:20]):  # print first 20
        print(f"  [{img['score']:>2}] {img['url'][:100]}  alt={img['alt'][:40]!r}")

    # Candidates for ingredient label (top-scored first)
    candidates = [img for img in images if img["score"] >= 0][:MAX_IMAGES_TO_ANALYSE * 3]
    if not candidates:
        candidates = images[:MAX_IMAGES_TO_ANALYSE * 3]

    print(f"\n--- Step 3: Reporting top image URLs likely to show ingredients ---")
    for img in candidates[:5]:
        print(f"  Score={img['score']} | {img['url']}")
        if img['alt']:
            print(f"           alt={img['alt']!r}")

    # -- Download and analyse images --
    print(f"\n--- Step 4 & 5: Downloading and sending to Claude Vision ---")
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    analysed = 0
    for idx, img in enumerate(candidates):
        if analysed >= MAX_IMAGES_TO_ANALYSE:
            break
        url = img["url"]
        # Derive local filename
        url_path = urlparse(url).path
        filename = Path(url_path).name or f"image_{idx}.jpg"
        # Keep only safe filename chars
        filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        local_path = DOWNLOAD_DIR / filename

        local = download_image(url, local_path)
        if not local:
            continue

        # Skip if file is tiny (likely a placeholder / icon / broken image)
        if local.stat().st_size < 10000:
            print(f"  Skipping — file too small ({local.stat().st_size} bytes), likely a placeholder.")
            continue

        inci_text = ask_claude_for_inci(local, client)
        results.append({
            "url": url,
            "local": str(local),
            "claude_response": inci_text,
        })
        analysed += 1

    # -- Print results --
    print("\n" + "=" * 70)
    print("RESULTS — INCI EXTRACTION")
    print("=" * 70)
    if not results:
        print("No images were successfully analysed.")
    for i, r in enumerate(results, 1):
        print(f"\n[Image {i}]")
        print(f"  Source URL : {r['url']}")
        print(f"  Local file : {r['local']}")
        print(f"\n  Claude's response:\n")
        for line in r["claude_response"].splitlines():
            print(f"    {line}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
