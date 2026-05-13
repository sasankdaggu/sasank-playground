"""LLM-based ingredient schema detection — Layer 1 of the ingredient pipeline.

For each brand website, this module:
  1. Discovers a sample product page URL (tries Shopify /products.json, then homepage link scan)
  2. Fetches the product page HTML (httpx first, Playwright fallback)
  3. Extracts ingredient-relevant HTML sections to reduce token usage
  4. Calls Claude claude-sonnet-4-6 to identify the CSS selector for the INCI list
  5. Validates the selector by actually extracting text from the page
  6. Stores the result in scraping.ingredient_strategies

Run via: python -m scraper.run_schema_detection
Re-run monthly or after scraping failures to refresh stale strategies.
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_DETECTION_MODEL = "claude-haiku-4-5-20251001"   # high rate limits; sufficient for HTML analysis
_MAX_HTML_CHARS = 20_000   # ~5K tokens — covers ingredient sections without burning quota


@dataclass
class DetectionResult:
    brand_domain: str
    brand_name: str
    brand_url: str
    platform: str | None
    css_selector: str | None
    requires_js: bool
    js_action: str | None
    notes: str | None
    sample_url: str | None
    sample_inci_preview: str | None
    confidence: float
    status: str   # 'active' | 'needs_review' | 'failed' | 'no_inci'


# ── Sample product URL discovery ──────────────────────────────────────────────

_SKINCARE_KEYWORDS = (
    "serum", "moisturiser", "moisturizer", "sunscreen", "spf", "cleanser",
    "face wash", "toner", "mask", "cream", "lotion", "gel", "oil", "balm",
    "eye cream", "essence", "mist", "exfoliant", "retinol", "niacinamide",
    "vitamin c", "hyaluronic", "salicylic", "aha", "bha", "peptide",
)
_NON_PRODUCT_HANDLES = (
    "delivery", "shipping", "gift", "free", "sample", "tester",
    "mystery", "surprise", "kit", "combo", "bundle", "set", "card", "pack-of",
    "duo", "value-set", "trial",
    "drink", "protein", "supplement", "tablet", "capsule", "syrup",  # non-skincare Himalaya-style
    "supercritical",  # single-ingredient supercritical extracts (Pure Arth Asia style)
    "sunscreen", "spf",  # Indian SPF products often use image INCI (regulatory) — prefer serums/cleansers for detection
)

_SHOPIFY_COLLECTION_SLUGS = (
    "all", "skincare", "face-care", "face", "moisturizers", "serums",
    "sunscreen", "cleansers", "toners",
)

_INGREDIENT_CLICK_SELECTORS = (
    'a:has-text("See Full Ingredients")',         # Dot & Key
    'button:has-text("See Full Ingredients")',
    'button:has-text("Full Ingredients")',
    'button:has-text("Ingredients")',
    'button:has-text("List of Ingredients")',
    'button:has-text("INGREDIENTS")',
    'a:has-text("INGREDIENTS")',                  # Hibiscus Monkey tab
    'summary:has-text("INGREDIENTS")',            # Beauty by Bie / The Derma Co style
    'summary:has-text("Ingredients")',
    'summary:has-text("Ingredient")',
    'summary:has-text("ingredient")',
    '[role="tab"]:has-text("Ingredient")',
    '[role="tab"]:has-text("INGREDIENT")',
    'li[role="tab"]:has-text("Ingredient")',
    'li:has-text("List of Ingredients")',
    '.accordion-header:has-text("Ingredient")',
    '.accordion__title:has-text("Ingredient")',
    '[data-toggle]:has-text("Ingredient")',
    '[class*="tab"]:has-text("Ingredient")',
    '[class*="tab"]:has-text("INGREDIENT")',
)


_FACE_CARE_KEYWORDS = (
    "serum", "moisturiser", "moisturizer", "cleanser",
    "face wash", "toner", "mask", "eye cream", "essence", "retinol",
    "niacinamide", "vitamin c", "hyaluronic", "salicylic", "aha", "bha",
    "face", "facial",
    # Excluding sunscreen/spf: Indian SPF products often have image INCI (regulatory),
    # so prefer serums/creams when selecting a sample product for detection.
)


def _pick_best_shopify_product(products: list[dict]) -> str | None:
    """Score each product by skincare relevance; prefer face care over body care."""
    best_handle, best_score = None, -1
    for p in products:
        handle = p.get("handle", "")
        title = (p.get("title") or "").lower()
        # Skip non-product listings
        if any(k in handle for k in _NON_PRODUCT_HANDLES):
            continue
        skincare_score = sum(1 for kw in _SKINCARE_KEYWORDS if kw in title)
        # Bonus for face-specific products — prefer these over generic body/hair
        face_bonus = 2 if any(kw in title for kw in _FACE_CARE_KEYWORDS) else 0
        score = skincare_score + face_bonus
        if score > best_score:
            best_score = score
            best_handle = handle
    # Fall back to first non-filtered handle
    if not best_handle:
        for p in products:
            handle = p.get("handle", "")
            if not any(k in handle for k in _NON_PRODUCT_HANDLES):
                best_handle = handle
                break
    return best_handle


async def _discover_shopify_collections(base_url: str) -> str | None:
    """Try common Shopify collection endpoints when /products.json returns empty."""
    root = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0, follow_redirects=True) as c:
            for slug in _SHOPIFY_COLLECTION_SLUGS:
                try:
                    r = await c.get(f"{root}/collections/{slug}/products.json?limit=50")
                    if r.status_code == 200:
                        data = r.json()
                        products = data.get("products", [])
                        if products:
                            handle = _pick_best_shopify_product(products)
                            if handle:
                                url = f"{root}/products/{handle}"
                                log.debug("shopify_collection_found", url=url, collection=slug)
                                return url
                except (httpx.TransportError, httpx.TimeoutException, json.JSONDecodeError):
                    continue
    except Exception:
        pass
    return None


_NON_PRODUCT_URL_SEGMENTS = (
    "/blog/", "/news/", "/tips/", "/article/", "/about/", "/contact/",
    "/login/", "/cart/", "/checkout/", "/account/", "/wishlist/", "/search/",
    "/faq/", "/terms/", "/privacy/", "/how-to/", "/skin-care-tips/",
    "/hair-care-tips/", "/reviews", "/ingredients",
)

def _pick_best_sitemap_product(sitemap_text: str, base_url: str) -> str | None:
    """Return the best skincare product URL found in sitemap XML."""
    parsed_base = urllib.parse.urlparse(base_url)
    base_netloc = parsed_base.netloc.lstrip("www.")
    locs = re.findall(r"<loc>(.*?)</loc>", sitemap_text)
    # Strict path patterns (high confidence = priority 10)
    _STRICT_PATHS = ("/product/", "/products/", "/p/", "/our-products/")
    candidates: list[tuple[int, str]] = []
    for loc in locs:
        loc = loc.strip()
        try:
            parsed = urllib.parse.urlparse(loc)
            if base_netloc not in parsed.netloc:
                continue
            # Skip review/query pages (e.g. mamaearth.in/product/name?id=X/reviews)
            if parsed.query:
                continue
            path = parsed.path.lower()
            if any(seg in path for seg in _NON_PRODUCT_URL_SEGMENTS):
                continue
            if any(k in path for k in _NON_PRODUCT_HANDLES):
                continue
            score = sum(1 for kw in _SKINCARE_KEYWORDS if kw.replace(" ", "-") in path or kw in path)
            depth = len([s for s in path.split("/") if s])
            in_strict = any(p in path for p in _STRICT_PATHS)
            # For strict paths like /our-products/, require depth ≥ 3 (brand/category/product)
            # to avoid matching category-level URLs like /our-products/serum
            if in_strict and depth < 3 and not any(p in path for p in ("/product/", "/products/", "/p/")):
                in_strict = False
            # Fallback: depth ≥ 3 segments + at least one skincare keyword (Neutrogena-style)
            if in_strict or (depth >= 3 and score >= 1):
                priority = 10 if in_strict else 0
                candidates.append((priority + score, loc))
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _pick_category_pages_from_sitemap(sitemap_text: str, base_url: str) -> list[str]:
    """When a sitemap has no product pages, return the most relevant category pages to scan."""
    parsed_base = urllib.parse.urlparse(base_url)
    base_netloc = parsed_base.netloc.lstrip("www.")
    locs = re.findall(r"<loc>(.*?)</loc>", sitemap_text)
    _CATEGORY_SKIP = ("/blog/", "/news/", "/tips/", "/about/", "/contact/", "/policy",
                      "/cart", "/search", "/account", "/collections.html")
    candidates: list[tuple[int, str]] = []
    for loc in locs:
        loc = loc.strip()
        try:
            parsed = urllib.parse.urlparse(loc)
            if base_netloc not in parsed.netloc:
                continue
            if parsed.query:
                continue
            path = parsed.path.lower()
            if any(skip in path for skip in _CATEGORY_SKIP):
                continue
            depth = len([s for s in path.split("/") if s])
            if depth < 1:
                continue
            score = sum(1 for kw in _SKINCARE_KEYWORDS if kw.replace(" ", "-") in path or kw in path)
            candidates.append((score * 10 + depth, loc))
        except Exception:
            continue
    candidates.sort(reverse=True)
    return [url for _, url in candidates[:5]]


async def _discover_from_sitemap(base_url: str) -> str | None:
    """Parse sitemap.xml (and product sub-sitemaps) to find a sample product URL."""
    parsed = urllib.parse.urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    to_try = [f"{root}/sitemap.xml", f"{root}/sitemap_products_1.xml"]
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0, follow_redirects=True) as c:
            for sitemap_url in to_try:
                try:
                    r = await c.get(sitemap_url)
                    if r.status_code != 200:
                        continue
                    # Follow product sub-sitemaps inside a sitemap index
                    for sub in re.findall(r"<loc>(.*?)</loc>", r.text):
                        sub = sub.strip()
                        if "product" in sub.lower() and sub.endswith(".xml"):
                            try:
                                r2 = await c.get(sub)
                                if r2.status_code == 200:
                                    url = _pick_best_sitemap_product(r2.text, base_url)
                                    if url:
                                        log.debug("sitemap_product_found", url=url)
                                        return url
                            except Exception:
                                continue
                    url = _pick_best_sitemap_product(r.text, base_url)
                    if url:
                        log.debug("sitemap_product_found", url=url)
                        return url
                    # Sitemap only has category pages (Forest Essentials style):
                    # pick the most skincare-relevant category page and scan it for product links
                    category_urls = _pick_category_pages_from_sitemap(r.text, base_url)
                    for cat_url in category_urls[:3]:
                        try:
                            rcat = await c.get(cat_url)
                            if rcat.status_code == 200:
                                prod_url = _find_product_link_in_html(rcat.text, base_url)
                                if prod_url and prod_url != cat_url:
                                    # Follow one more level if still category-depth
                                    last_seg = prod_url.rstrip("/").split("/")[-1].replace(".html", "")
                                    if prod_url.endswith(".html") and len(last_seg) < 25:
                                        try:
                                            rcat2 = await c.get(prod_url)
                                            if rcat2.status_code == 200:
                                                prod_url2 = _find_product_link_in_html(rcat2.text, base_url)
                                                if prod_url2 and prod_url2 != prod_url:
                                                    prod_url = prod_url2
                                        except Exception:
                                            pass
                                    log.debug("sitemap_category_product_found", url=prod_url, category=cat_url)
                                    return prod_url
                        except Exception:
                            continue
                except (httpx.TransportError, httpx.TimeoutException):
                    continue
    except Exception:
        pass
    return None


async def _discover_from_listing_page(base_url: str) -> str | None:
    """Fetch common product listing pages and scan for product links.

    Also handles .html category sites (Forest Essentials style): if the first
    matched link is itself a category page, follows it one level deeper.
    """
    root = base_url.rstrip("/")
    listing_paths = ("/shop", "/products", "/all", "/skincare", "/face-care",
                     "/facial-care/serums.html", "/facial-care/moisturisers.html")
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0, follow_redirects=True) as c:
            for path in listing_paths:
                try:
                    r = await c.get(f"{root}{path}")
                    if r.status_code != 200 or len(r.text) < 1000:
                        continue
                    url = _find_product_link_in_html(r.text, base_url)
                    if not url:
                        continue
                    log.debug("listing_page_product_found", url=url, path=path)
                    # For .html category-style sites (Forest Essentials): follow up to 2 levels
                    # deeper until we reach a product URL (longer, more specific slug)
                    for _ in range(2):
                        last_seg = url.rstrip("/").split("/")[-1].replace(".html", "")
                        if not url.endswith(".html") or len(last_seg) >= 30:
                            break  # looks like a real product URL
                        try:
                            r2 = await c.get(url)
                            if r2.status_code != 200:
                                break
                            deeper = _find_product_link_in_html(r2.text, base_url)
                            if not deeper or deeper == url:
                                break
                            url = deeper
                        except Exception:
                            break
                    return url
                except (httpx.TransportError, httpx.TimeoutException):
                    continue
    except Exception:
        pass
    return None


async def discover_sample_product_url(base_url: str) -> tuple[str | None, str | None]:
    """Return (product_url, platform). platform is 'shopify' or 'custom' or None."""
    # Shopify: /products.json is always available and fast
    shopify_url = base_url.rstrip("/") + "/products.json?limit=50"
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0, follow_redirects=True) as c:
            r = await c.get(shopify_url)
        if r.status_code == 200:
            try:
                data = r.json()
                products = data.get("products", [])
                if products:
                    handle = _pick_best_shopify_product(products)
                    if handle:
                        product_url = base_url.rstrip("/") + f"/products/{handle}"
                        log.debug("shopify_product_found", url=product_url)
                        return product_url, "shopify"
            except (json.JSONDecodeError, KeyError):
                pass
    except (httpx.TransportError, httpx.TimeoutException):
        pass

    # 2. Shopify collections fallback (some stores have empty /products.json)
    url = await _discover_shopify_collections(base_url)
    if url:
        return url, "shopify"

    # 3. Sitemap-based discovery (covers non-Shopify brands with sitemap.xml)
    url = await _discover_from_sitemap(base_url)
    if url:
        return url, "custom"

    # 4. Homepage link scan
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0, follow_redirects=True) as c:
            r = await c.get(base_url)
        if r.status_code == 200:
            product_url = _find_product_link_in_html(r.text, base_url)
            if product_url:
                return product_url, "custom"
    except (httpx.TransportError, httpx.TimeoutException):
        pass

    # 5. Product listing page scan (/shop, /all, etc.)
    url = await _discover_from_listing_page(base_url)
    if url:
        return url, "custom"

    return None, None


def _find_product_link_in_html(html: str, base_url: str) -> str | None:
    """Find the most skincare-relevant product page link in a homepage's HTML."""
    parsed = urllib.parse.urlparse(base_url)
    domain_root = f"{parsed.scheme}://{parsed.netloc}"

    _PRODUCT_PATTERNS = [
        r'href=["\']((?:https?://[^\'"]+)?/(?:products?|p|item|detail)/[^\'"<>?#]{5,})["\']',
        r'href=["\']((?:https?://[^\'"]+)?/[^\'"<>?#]{5,}/p/\d+)["\']',
        # .html product pages with ≥3 path segments (Forest Essentials, Garnier style)
        r'href=["\']((?:https?://[^\'"]+)?/[^\'"<>?#/]{3,}/[^\'"<>?#/]{3,}/[^\'"<>?#]{5,}\.html)["\']',
    ]
    _COLLECTION_WORDS = ("/collection", "/category", "/shop/", "/catalog", "/all-products",
                         "/skincare", "/face-care", "#", "javascript:")

    candidates: list[tuple[int, str]] = []
    for pattern in _PRODUCT_PATTERNS:
        for m in re.finditer(pattern, html, re.IGNORECASE):
            href = m.group(1)
            if any(w in href.lower() for w in _COLLECTION_WORDS):
                continue
            if not href.startswith("http"):
                href = domain_root + href
            # Score by skincare keywords in the URL slug
            slug = href.lower()
            score = sum(1 for kw in _SKINCARE_KEYWORDS if kw.replace(" ", "-") in slug)
            candidates.append((score, href))

    if not candidates:
        return None
    # Return highest-scoring candidate (most skincare-relevant URL slug)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ── Page fetch ────────────────────────────────────────────────────────────────

async def fetch_page_html(url: str, use_playwright: bool = False) -> str:
    if use_playwright:
        return await _fetch_playwright(url)
    return await _fetch_httpx(url)


async def _fetch_httpx(url: str) -> str:
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return ""
            await asyncio.sleep(3 * (attempt + 1))
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt == 2:
                return ""
            await asyncio.sleep(3 * (attempt + 1))
    return ""


async def _fetch_playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=_HEADERS["User-Agent"],
                locale="en-IN",
            )
            page = await ctx.new_page()
            await Stealth().apply_stealth_async(page)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                await page.wait_for_timeout(3_000)
                # Scroll to trigger IntersectionObserver lazy-loaded sections (e.g. Aqualogica)
                await page.evaluate('window.scrollTo(0, 3000)')
                await page.wait_for_timeout(1_500)
                await page.evaluate('window.scrollTo(0, 6000)')
                await page.wait_for_timeout(1_500)
                html = await page.content()
            finally:
                await page.close()
            await browser.close()
            return html
    except Exception as exc:
        log.warning("playwright_fetch_failed", url=url, error=str(exc))
        return ""


async def _fetch_playwright_with_click(url: str) -> str:
    """Load via Playwright, scroll to trigger lazy loading, then click ingredient sections."""
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=_HEADERS["User-Agent"],
                locale="en-IN",
            )
            page = await ctx.new_page()
            await Stealth().apply_stealth_async(page)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                await page.wait_for_timeout(3_000)
                # Scroll down to trigger IntersectionObserver lazy-loaded sections
                await page.evaluate('window.scrollTo(0, 3000)')
                await page.wait_for_timeout(1_500)
                await page.evaluate('window.scrollTo(0, 6000)')
                await page.wait_for_timeout(1_500)
                await page.evaluate('window.scrollTo(0, 0)')
                await page.wait_for_timeout(500)
                for sel in _INGREDIENT_CLICK_SELECTORS:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=1_500):
                            # Skip <a> links that would navigate away (not same-page anchors)
                            tag = await el.evaluate('el => el.tagName.toLowerCase()')
                            if tag == 'a':
                                href = await el.evaluate('el => el.getAttribute("href") || ""')
                                if href and not href.startswith('#'):
                                    continue
                            await el.scroll_into_view_if_needed()
                            await el.click()
                            await page.wait_for_timeout(3_000)
                            log.debug("ingredient_click_success", url=url, clicked_sel=sel)
                            break
                    except Exception:
                        continue
                html = await page.content()
            finally:
                await page.close()
            await browser.close()
            return html
    except Exception as exc:
        log.warning("playwright_click_failed", url=url, error=str(exc))
        return ""


# ── HTML pre-processing ───────────────────────────────────────────────────────

def extract_ingredient_sections(html: str) -> str:
    """Extract sections of HTML likely to contain ingredient information.

    Reduces token usage by ~80% vs sending the full page.
    Strategy: include all text within 3000 chars of any 'ingredient' keyword occurrence.
    """
    if len(html) <= _MAX_HTML_CHARS:
        return html

    # Strip <script> and <style> blocks first (large, never contain INCI)
    stripped = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    stripped = re.sub(r"<style[^>]*>.*?</style>", " ", stripped, flags=re.DOTALL | re.IGNORECASE)

    if len(stripped) <= _MAX_HTML_CHARS:
        return stripped

    # Find positions of ingredient-related keywords
    positions = [m.start() for m in re.finditer(
        r"(?:ingredient|inci|full.ingredi|all.ingredi|aqua|water\/aqua)",
        stripped, re.IGNORECASE
    )]

    if not positions:
        # No ingredient keywords — return the first MAX_HTML_CHARS of stripped HTML
        return stripped[:_MAX_HTML_CHARS]

    # Build a set of character ranges to include (3000 chars around each match)
    ranges: list[tuple[int, int]] = []
    for pos in positions:
        start = max(0, pos - 1500)
        end = min(len(stripped), pos + 1500)
        ranges.append((start, end))

    # Merge overlapping ranges and concatenate
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for s, e in ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    sections = "\n\n...\n\n".join(stripped[s:e] for s, e in merged)
    return sections[:_MAX_HTML_CHARS]


# ── LLM detection ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert at analyzing skincare brand website HTML to find the INCI ingredient list on product detail pages.

The INCI ingredient list is the complete chemical ingredient list — a comma-separated sequence of standardized INCI names (e.g., "Aqua, Glycerin, Niacinamide, Phenoxyethanol..."). It differs from:
- "hero ingredients" (marketing copy listing 2-5 star ingredients with benefits)
- "key ingredients" (same — marketing, not full INCI)
- directions / how to use
- warnings

Your goal: find the CSS selector for the HTML element whose text content IS or CONTAINS the full INCI list."""

_USER_PROMPT_TEMPLATE = """Analyze this product page HTML from {url} and find the full INCI ingredient list.

HTML (may be truncated):
```html
{html_snippet}
```

Return a JSON object ONLY (no markdown fences, no prose):
{{
  "selector": "<CSS selector for the element containing the full INCI list, or null if not found>",
  "requires_js": <true if the INCI list is loaded via JavaScript and not present in this HTML, false otherwise>,
  "js_action": "<null, or a description of what JS interaction reveals the INCI, e.g. 'click .see-full-ingredients button'>",
  "text_found": "<first 150 chars of the INCI text if found in this HTML, else null>",
  "confidence": <float 0.0-1.0>,
  "notes": "<any important notes about extraction, edge cases, or why selector was chosen>"
}}

Rules:
- The selector must target the element whose text content is the INCI list itself (not a parent container with lots of other content).
- If multiple elements could match, pick the most specific one.
- If the INCI is inside a collapsed/hidden accordion that IS present in the static HTML, requires_js=false (it's just CSS-hidden, not JS-rendered).
- Set requires_js=true only if the element does not appear anywhere in the HTML at all.
- If no INCI is found and the site appears to show ingredients only as product images, set selector=null and notes="INCI only available as product image".
"""


def _repair_json(text: str) -> str:
    """Trim a potentially-truncated JSON object to its last complete closing brace."""
    last_brace = text.rfind("}")
    if last_brace == -1:
        return text
    return text[: last_brace + 1]


async def detect_via_llm(
    html_snippet: str,
    url: str,
    anthropic_api_key: str,
) -> dict:
    prompt = _USER_PROMPT_TEMPLATE.format(url=url, html_snippet=html_snippet)
    payload = {
        "model": _DETECTION_MODEL,
        "max_tokens": 1024,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.post(_ANTHROPIC_API_URL, json=payload, headers=headers)
            if r.status_code == 200:
                content = r.json()["content"][0]["text"].strip()
                # Strip markdown code fences if model added them
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                # Repair truncated JSON: trim to last complete }
                content = _repair_json(content)
                return json.loads(content)
            if r.status_code == 429:
                wait = 15 * (2 ** attempt)   # 15s, 30s, 60s, 120s
                log.warning("llm_rate_limited", url=url, attempt=attempt, wait_s=wait)
                await asyncio.sleep(wait)
                continue
            log.warning("llm_api_error", status=r.status_code, body=r.text[:200])
            return {}
        except (httpx.TransportError, httpx.TimeoutException, json.JSONDecodeError) as exc:
            if attempt == 3:
                log.warning("llm_detection_failed", url=url, error=str(exc))
                return {}
            await asyncio.sleep(5 * (attempt + 1))
    return {}


# ── Validation ────────────────────────────────────────────────────────────────

def validate_selector(selector: str, html: str) -> str | None:
    """Extract text using a CSS selector expressed as a simple regex equivalent.

    Supports: element.class, element#id, .class, element[attr=val],
    element:nth-of-type(N) sub_selector, descendant (space) combinator,
    and > child combinator (with proper parent-child navigation).
    Returns the extracted text (stripped), or None if selector doesn't match.
    """
    if not selector:
        return None

    selector = selector.strip()

    # Handle :nth-of-type(N) and :nth-child(N) at selector start
    # e.g. "accordion-tab:nth-of-type(3) .accordion__content p"
    # e.g. "li:nth-child(2) > span > span:nth-of-type(1)"
    nth_m = re.match(r'^([\w-]+):nth-(?:of-type|child)\((\d+)\)(.*)', selector)
    if nth_m:
        tag = nth_m.group(1)
        nth = int(nth_m.group(2))
        remainder = nth_m.group(3).strip().lstrip('>').strip()
        all_elements = re.findall(
            rf'<{re.escape(tag)}[^>]*>(.*?)</{re.escape(tag)}>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if len(all_elements) < nth:
            return None
        sub_html = all_elements[nth - 1]
        return validate_selector(remainder, sub_html) if remainder else (
            re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', sub_html)).strip() or None
        )

    # Handle descendant combinator (space-separated, no >) e.g. ".accordion__content p"
    # Strategy: find each parent opening tag, search for the child within 10k chars,
    # return the first result that looks like INCI (avoids matching wrong accordion sections).
    if ">" not in selector:
        space_parts = selector.split(None, 1)
        if len(space_parts) == 2:
            parent_open_pat = _selector_to_open_regex(space_parts[0])
            if parent_open_pat:
                for parent_m in re.finditer(parent_open_pat, html, re.DOTALL | re.IGNORECASE):
                    sub_html = html[parent_m.start(): parent_m.start() + 50_000]
                    result = validate_selector(space_parts[1], sub_html)
                    if result and _looks_like_inci(result):
                        return result
                # If nothing INCI-like found, fall through to > chain handling

    # Handle > chain: "parent > child" — navigate parent-child properly.
    # For multi-segment chains, find each parent opening tag position, search
    # the next 5k chars for the child, return the first INCI-like result.
    parts = [p.strip() for p in selector.split(">")]
    if len(parts) >= 2:
        parent_open_pat = _selector_to_open_regex(parts[0])
        if parent_open_pat:
            child_sel = " > ".join(parts[1:])  # remaining chain
            for parent_m in re.finditer(parent_open_pat, html, re.DOTALL | re.IGNORECASE):
                sub_html = html[parent_m.start(): parent_m.start() + 5_000]
                result = validate_selector(child_sel, sub_html)
                if result and _looks_like_inci(result):
                    return result
        # Fall through to last-segment approach if parent navigation found nothing

    sel = parts[-1]
    pattern = _selector_to_regex(sel)
    if not pattern:
        return None

    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if not match:
        return None

    raw = match.group(1)
    text = re.sub(r"<[^>]+>", "", raw)          # strip tags
    text = re.sub(r"&[a-z]+;", " ", text)        # unescape entities roughly
    text = re.sub(r"\s+", " ", text).strip()     # normalize whitespace
    return text if len(text) > 20 else None


def _selector_to_open_regex(selector: str) -> str | None:
    """Return a regex that matches only the OPENING tag of a selector (no content capture)."""
    parts = [p.strip() for p in selector.split(">")]
    # Strip pseudo-classes like :nth-child(N), :nth-of-type(N) from the segment
    sel = re.sub(r':nth-(?:of-type|child)\(\d+\)', '', parts[-1]).strip()
    m = re.match(r'^(\w[\w-]*)?(?:\.([a-zA-Z0-9_!:/\\-]+))?(?:#([a-zA-Z0-9_-]+))?$', sel)
    if not m:
        # class-based attribute selector: div[class*="something"]
        attr_m = re.match(r'^(\w[\w-]*)?\[class[\*~^$|]?="([^"]+)"\]$', sel)
        if attr_m:
            tag = attr_m.group(1) or r'\w+'
            val = re.escape(attr_m.group(2))
            return rf'<{tag}[^>]*class="[^"]*{val}[^"]*"[^>]*>'
        # Generic attribute selector: tag[attr], tag[attr="val"], tag[attr*="val"]
        gen_m = re.match(r'^(\w[\w-]*)?\[([a-zA-Z][\w-]*)(?:([\*~^$|]?)="([^"]*)")?\]$', sel)
        if gen_m:
            tag = re.escape(gen_m.group(1)) if gen_m.group(1) else r'\w+'
            aname = re.escape(gen_m.group(2))
            operator = gen_m.group(3) or ''
            aval = gen_m.group(4)
            if aval is None:
                # Presence-only [attr]: matches attr="", attr="true", attr, etc.
                return rf'<{tag}[^>]*\b{aname}(?:=[^\s>]*)?\b[^>]*>'
            elif not aval:
                # Empty-string value [attr=""]: matches exactly open="" or open=''
                return rf'<{tag}[^>]*\b{aname}=["\']["\'][^>]*>'
            elif operator == '*':
                return rf'<{tag}[^>]*\b{aname}=["\'][^"\']*{re.escape(aval)}[^"\']*["\'][^>]*>'
            else:
                return rf'<{tag}[^>]*\b{aname}=["\']?{re.escape(aval)}["\']?[^>]*>'
        return None
    tag = m.group(1) or r'\w+'
    cls = m.group(2)
    eid = m.group(3)
    if cls:
        return rf'<{tag}[^>]*class="[^"]*\b{re.escape(cls)}\b[^"]*"[^>]*>'
    if eid:
        return rf'<{tag}[^>]*id="{re.escape(eid)}"[^>]*>'
    return rf'<{re.escape(tag)}[^>]*>'


def _selector_to_regex(selector: str) -> str | None:
    """Convert a simple CSS selector to a regex that extracts element content.

    Handles: div.classname, span.class, .class-name, div[class*=something],
    details.class > div.class (takes the last part of a > chain).
    Class names may include Tailwind special chars: !, :, /, \\
    """
    # Take the last segment of a > chain; strip pseudo-classes for regex matching
    parts = [p.strip() for p in selector.split(">")]
    sel = re.sub(r':nth-(?:of-type|child)\(\d+\)', '', parts[-1]).strip()

    # Parse element + class/id
    m = re.match(r'^(\w[\w-]*)?(?:\.([a-zA-Z0-9_!:/\\-]+))?(?:#([a-zA-Z0-9_-]+))?$', sel)
    if not m:
        # Try attribute selector: div[attr*="something"] or div[class*="something"]
        attr_m = re.match(r'^(\w[\w-]*)?\[([\w-]+)([\*~^$|]?)="([^"]+)"\]$', sel)
        if attr_m:
            tag = attr_m.group(1) or r'\w+'
            attr = attr_m.group(2)
            op = attr_m.group(3)
            val = re.escape(attr_m.group(4))
            if op in ('*', '~', '^', '$', '|', ''):
                # substring/word/prefix/suffix/dash match — use substring for regex simplicity
                attr_pat = rf'{re.escape(attr)}="[^"]*{val}[^"]*"'
            else:
                attr_pat = rf'{re.escape(attr)}="{val}"'
            return rf'<{tag}[^>]*{attr_pat}[^>]*>(.*?)</{tag}\s*>'
        return None

    tag = m.group(1) or r'\w+'
    cls = m.group(2)
    eid = m.group(3)

    if cls:
        # Use \b word boundaries so class="ingredient" doesn't match class="ingredients-popup"
        return rf'<{tag}[^>]*class="[^"]*\b{re.escape(cls)}\b[^"]*"[^>]*>(.*?)</{tag}\s*>'
    if eid:
        return rf'<{tag}[^>]*id="{re.escape(eid)}"[^>]*>(.*?)</{tag}\s*>'
    return rf'<{re.escape(tag)}[^>]*>(.*?)</{re.escape(tag)}\s*>'


_KNOWN_INCI = [
    "aqua", "glycerin", "phenoxyethanol", "niacinamide", "acid",
    "ethanol", "propanediol", "butylene glycol", "tocopherol",
    "squalane", "squalene", "ceramide", "retinol", "ascorbic",
    "hyaluronic", "panthenol", "allantoin", "centella", "niacinamide",
]
_PROSE_MARKERS = ("it ", "this ", "our ", "helps ", "provides ", "is a ", "extract", "sourced from", "derived from")


def _looks_like_inci(text: str) -> bool:
    """Return True if text looks like a real INCI list (not marketing copy or CSS)."""
    if not text or len(text) < 8:
        return False
    # Reject CSS/JS content — but allow {Word} botanical INCI notation (e.g. {Flower}, {Leaf})
    head = text[:100]
    if any(marker in head for marker in ("Skip to content", "shopify-section", "function(")):
        return False
    if "{" in head and not re.search(r'\{[A-Za-z]+\}', head):
        return False
    tl = text.lower()
    comma_count = text.count(",")
    inci_terms = sum(1 for t in _KNOWN_INCI if t in tl)
    # Standard multi-ingredient list
    if comma_count >= 5 or (comma_count >= 2 and inci_terms >= 2) or inci_terms >= 5:
        return True
    # Single-ingredient product: short text, known INCI term, no prose markers
    if inci_terms >= 1 and len(text) <= 200 and not any(m in tl for m in _PROSE_MARKERS):
        return True
    return False


# ── Main detection orchestrator ───────────────────────────────────────────────

async def detect_brand_strategy(
    brand_url: str,
    brand_name: str,
    anthropic_api_key: str,
    force_playwright: bool = False,
) -> DetectionResult:
    """Run full detection for a brand. Returns a DetectionResult ready for DB storage."""
    domain = _extract_domain(brand_url)
    log.info("detection_start", brand=brand_name, domain=domain)

    # Step 1: find a sample product URL
    sample_url, platform = await discover_sample_product_url(brand_url)
    if not sample_url:
        log.warning("no_sample_product_url", brand=brand_name)
        return DetectionResult(
            brand_domain=domain, brand_name=brand_name, brand_url=brand_url,
            platform=None, css_selector=None, requires_js=False, js_action=None,
            notes="Could not discover a sample product URL",
            sample_url=None, sample_inci_preview=None, confidence=0.0, status="failed",
        )

    # Step 2: fetch page HTML
    html = await fetch_page_html(sample_url, use_playwright=force_playwright)
    if not html and not force_playwright:
        html = await fetch_page_html(sample_url, use_playwright=True)
        if html:
            force_playwright = True

    if not html:
        return DetectionResult(
            brand_domain=domain, brand_name=brand_name, brand_url=brand_url,
            platform=platform, css_selector=None, requires_js=False, js_action=None,
            notes="Could not fetch sample product page",
            sample_url=sample_url, sample_inci_preview=None, confidence=0.0, status="failed",
        )

    # Step 3: extract ingredient-relevant HTML sections
    snippet = extract_ingredient_sections(html)

    # Step 4: call LLM
    llm_result = await detect_via_llm(snippet, sample_url, anthropic_api_key)
    if not llm_result:
        return DetectionResult(
            brand_domain=domain, brand_name=brand_name, brand_url=brand_url,
            platform=platform, css_selector=None, requires_js=False, js_action=None,
            notes="LLM detection returned no result",
            sample_url=sample_url, sample_inci_preview=None, confidence=0.0, status="failed",
        )

    selector = llm_result.get("selector")
    requires_js = bool(llm_result.get("requires_js", False))
    confidence = float(llm_result.get("confidence", 0.0))
    notes = llm_result.get("notes")
    js_action = llm_result.get("js_action")
    text_found = llm_result.get("text_found")

    # Step 5: if requires_js and we haven't used Playwright, re-fetch with it
    if requires_js and not force_playwright:
        log.info("js_required_refetch", brand=brand_name, url=sample_url)
        playwright_html = await fetch_page_html(sample_url, use_playwright=True)
        if playwright_html:
            html = playwright_html
            snippet2 = extract_ingredient_sections(html)
            llm_result2 = await detect_via_llm(snippet2, sample_url, anthropic_api_key)
            # Only adopt second result if it's better than (or supplements) the first
            if llm_result2 and llm_result2.get("selector"):
                selector = llm_result2.get("selector")
                confidence = float(llm_result2.get("confidence", confidence))
                notes = llm_result2.get("notes", notes)
                js_action = llm_result2.get("js_action", js_action)
                text_found = llm_result2.get("text_found", text_found)
                requires_js = bool(llm_result2.get("requires_js", False))
            elif llm_result2 and not selector:
                # First result had no selector; use second result even without selector
                confidence = float(llm_result2.get("confidence", confidence))
                notes = llm_result2.get("notes", notes)
                text_found = llm_result2.get("text_found") or text_found

    # Step 5b: still no selector → Playwright + ingredient click as last resort
    if not selector:
        log.info("playwright_click_fallback", brand=brand_name, url=sample_url)
        click_html = await _fetch_playwright_with_click(sample_url)
        if click_html:
            html = click_html
            snippet_click = extract_ingredient_sections(click_html)
            llm_click = await detect_via_llm(snippet_click, sample_url, anthropic_api_key)
            if llm_click:
                if llm_click.get("selector"):
                    selector = llm_click["selector"]
                    requires_js = True
                confidence = max(confidence, float(llm_click.get("confidence", 0.0)))
                notes = llm_click.get("notes", notes)
                js_action = llm_click.get("js_action") or js_action
                text_found = llm_click.get("text_found") or text_found

    # Step 6: validate selector
    inci_preview = None
    if selector:
        extracted = validate_selector(selector, html)
        if extracted and _looks_like_inci(extracted):
            inci_preview = extracted[:200]
        elif text_found and _looks_like_inci(text_found):
            inci_preview = text_found[:200]
    elif text_found and _looks_like_inci(text_found):
        inci_preview = text_found[:200]

    # Step 7: determine status
    if not selector:
        if "image" in (notes or "").lower():
            status = "no_inci"
        else:
            status = "needs_review" if confidence > 0.3 else "failed"
    elif inci_preview:
        status = "active" if confidence >= 0.7 else "needs_review"
    else:
        status = "needs_review"

    log.info("detection_complete",
             brand=brand_name, status=status, selector=selector,
             confidence=confidence, preview=inci_preview[:60] if inci_preview else None)

    return DetectionResult(
        brand_domain=domain,
        brand_name=brand_name,
        brand_url=brand_url,
        platform=platform,
        css_selector=selector,
        requires_js=requires_js,
        js_action=js_action,
        notes=notes,
        sample_url=sample_url,
        sample_inci_preview=inci_preview,
        confidence=confidence,
        status=status,
    )


def _extract_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lstrip("www.")
    return domain or url


# ── DB persistence ────────────────────────────────────────────────────────────

async def upsert_strategy(conn, result: DetectionResult) -> None:
    import psycopg
    async with conn.cursor() as cur:
        await cur.execute("""
            INSERT INTO scraping.ingredient_strategies
              (brand_domain, brand_name, brand_url, platform,
               css_selector, requires_js, js_action, notes,
               sample_url, sample_inci_preview, confidence,
               detection_model, detected_at, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s)
            ON CONFLICT (brand_domain) DO UPDATE SET
              brand_name        = EXCLUDED.brand_name,
              brand_url         = EXCLUDED.brand_url,
              platform          = EXCLUDED.platform,
              css_selector      = EXCLUDED.css_selector,
              requires_js       = EXCLUDED.requires_js,
              js_action         = EXCLUDED.js_action,
              notes             = EXCLUDED.notes,
              sample_url        = EXCLUDED.sample_url,
              sample_inci_preview = EXCLUDED.sample_inci_preview,
              confidence        = EXCLUDED.confidence,
              detection_model   = EXCLUDED.detection_model,
              detected_at       = now(),
              status            = EXCLUDED.status
        """, (
            result.brand_domain, result.brand_name, result.brand_url,
            result.platform, result.css_selector, result.requires_js,
            result.js_action, result.notes, result.sample_url,
            result.sample_inci_preview, result.confidence,
            _DETECTION_MODEL, result.status,
        ))
    await conn.commit()
