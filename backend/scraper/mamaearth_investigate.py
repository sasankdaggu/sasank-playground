"""
Mamaearth INCI ingredient extraction investigation script.
Investigates 5 approaches to extract ingredient list from Mamaearth product pages.
"""

import asyncio
import json
import re
import sys
from urllib.parse import urlparse

PRODUCT_URL = "https://mamaearth.in/product/vitamin-c-face-wash-with-vitamin-c-and-turmeric-for-skin-illumination-100ml"

# Common INCI ingredient markers
INCI_MARKERS = ["aqua", "water", "glycerin", "niacinamide", "sodium", "potassium",
                "phenoxyethanol", "parfum", "fragrance", "tocopherol", "citric acid",
                "disodium", "hydroxide", "ascorbic", "turmeric", "curcuma"]


def looks_like_inci(text: str) -> bool:
    """Heuristic: does this text look like an INCI ingredient list?"""
    if not text or len(text) < 30:
        return False
    lower = text.lower()
    hits = sum(1 for m in INCI_MARKERS if m in lower)
    return hits >= 3


def find_inci_in_json(obj, path="root", depth=0, results=None):
    """Recursively search JSON object for INCI-like text."""
    if results is None:
        results = []
    if depth > 15:
        return results
    if isinstance(obj, str):
        if looks_like_inci(obj):
            results.append((path, obj[:300]))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_inci_in_json(v, f"{path}.{k}", depth + 1, results)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:50]):  # limit list scanning
            find_inci_in_json(item, f"{path}[{i}]", depth + 1, results)
    return results


async def run_investigation():
    from playwright.async_api import async_playwright
    import httpx

    print("=" * 70)
    print("MAMAEARTH INCI INGREDIENT EXTRACTION INVESTIGATION")
    print(f"URL: {PRODUCT_URL}")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # APPROACH 1 & 2 & 3 & 4: Use Playwright to get fully-rendered page
    # (React SSR means __NEXT_DATA__ is in the initial HTML, but let's
    # confirm with both raw HTTP and rendered DOM)
    # ------------------------------------------------------------------ #

    raw_html = None
    rendered_html = None
    network_api_calls = []
    console_logs = []

    print("\n[*] Fetching raw HTML via httpx (no JS execution)...")
    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
        follow_redirects=True,
        timeout=30,
    ) as client:
        try:
            resp = await client.get(PRODUCT_URL)
            raw_html = resp.text
            print(f"    Status: {resp.status_code}, Size: {len(raw_html):,} bytes")
        except Exception as e:
            print(f"    ERROR: {e}")

    print("\n[*] Launching Playwright (headed=false) to render page + capture network...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        # Capture network requests that look like API calls
        async def on_response(response):
            url = response.url
            if any(x in url for x in ["/api/", "/graphql", "product", "ingredient"]):
                try:
                    body = await response.body()
                    if len(body) < 5_000_000:  # skip huge responses
                        try:
                            parsed = json.loads(body)
                            network_api_calls.append({
                                "url": url,
                                "status": response.status,
                                "body_json": parsed,
                                "body_size": len(body),
                            })
                        except Exception:
                            text = body.decode("utf-8", errors="replace")
                            if looks_like_inci(text):
                                network_api_calls.append({
                                    "url": url,
                                    "status": response.status,
                                    "body_text": text[:500],
                                    "body_size": len(body),
                                })
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            await page.goto(PRODUCT_URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"    WARNING during goto: {e}")
            try:
                await page.wait_for_timeout(5000)
            except Exception:
                pass

        rendered_html = await page.content()
        print(f"    Rendered HTML size: {len(rendered_html):,} bytes")

        # Also grab any window globals
        js_globals = await page.evaluate("""
            () => {
                const result = {};
                const keys = ['__NEXT_DATA__', '__INITIAL_STATE__', '__REDUX_STATE__',
                              '__APP_STATE__', '__PRELOADED_STATE__', 'window.__data__',
                              '__NUXT__', '__STATE__'];
                for (const k of keys) {
                    try {
                        const val = window[k];
                        if (val !== undefined) result[k] = val;
                    } catch(e) {}
                }
                return result;
            }
        """)

        await browser.close()

    # ================================================================== #
    # APPROACH 1: __NEXT_DATA__ script tag
    # ================================================================== #
    print("\n" + "=" * 70)
    print("APPROACH 1: __NEXT_DATA__ script tag")
    print("=" * 70)

    html_to_search = rendered_html or raw_html or ""

    next_data_match = re.search(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html_to_search,
        re.DOTALL,
    )

    if next_data_match:
        print("  FOUND __NEXT_DATA__ script tag!")
        raw_json = next_data_match.group(1).strip()
        print(f"  Raw JSON size: {len(raw_json):,} bytes")
        try:
            data = json.loads(raw_json)
            inci_hits = find_inci_in_json(data)
            if inci_hits:
                print(f"  INCI-like text found at {len(inci_hits)} location(s):")
                for path, sample in inci_hits:
                    print(f"\n    Path: {path}")
                    print(f"    Sample: {sample[:400]}")
                print("\n  ROBUSTNESS: HIGH — __NEXT_DATA__ is a Next.js standard, stable across builds.")
                print("  HOW TO EXTRACT: Parse JSON → navigate to the path shown above.")
            else:
                print("  __NEXT_DATA__ found but NO INCI-like text within it.")
                # Show top-level keys to help debug
                if isinstance(data, dict):
                    print(f"  Top-level keys: {list(data.keys())[:10]}")
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}")
    else:
        print("  NOT FOUND in rendered HTML.")
        # Try raw HTML too
        if raw_html:
            raw_match = re.search(
                r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                raw_html, re.DOTALL,
            )
            if raw_match:
                print("  BUT FOUND in raw (non-rendered) HTML — SSR confirmed.")
            else:
                print("  Also NOT FOUND in raw HTTP response — not a Next.js SSR page.")

    # Also check window globals captured by Playwright
    if js_globals:
        print(f"\n  Window globals found: {list(js_globals.keys())}")
        if "__NEXT_DATA__" in js_globals:
            inci_hits = find_inci_in_json(js_globals["__NEXT_DATA__"])
            if inci_hits:
                print("  INCI also confirmed via window.__NEXT_DATA__:")
                for path, sample in inci_hits[:2]:
                    print(f"    {path}: {sample[:200]}")

    # ================================================================== #
    # APPROACH 2: window.__INITIAL_STATE__ and similar globals
    # ================================================================== #
    print("\n" + "=" * 70)
    print("APPROACH 2: window.__INITIAL_STATE__ / global JS variables")
    print("=" * 70)

    # Search in raw HTML for inline script blocks
    inline_script_matches = re.findall(
        r'<script[^>]*>(.*?)</script>',
        html_to_search,
        re.DOTALL,
    )
    global_var_patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        r'window\.__REDUX_STATE__\s*=\s*({.*?});',
        r'window\.__APP_STATE__\s*=\s*({.*?});',
        r'window\.__PRELOADED_STATE__\s*=\s*({.*?});',
        r'__STATE__\s*=\s*({.*?});',
    ]

    found_globals = {}
    for script_content in inline_script_matches:
        for pat in global_var_patterns:
            m = re.search(pat, script_content, re.DOTALL)
            if m:
                key = pat.split("=")[0].strip().replace("window.", "").strip()
                try:
                    found_globals[key] = json.loads(m.group(1))
                except Exception:
                    found_globals[key] = m.group(1)[:200]

    # Also check what Playwright found
    for k, v in js_globals.items():
        if k != "__NEXT_DATA__" and k not in found_globals:
            found_globals[k] = v

    if found_globals:
        print(f"  Found globals: {list(found_globals.keys())}")
        for key, val in found_globals.items():
            inci_hits = find_inci_in_json(val, key)
            if inci_hits:
                print(f"  INCI found in {key}:")
                for path, sample in inci_hits[:2]:
                    print(f"    {path}: {sample[:300]}")
            else:
                print(f"  {key}: No INCI-like content found.")
        print("\n  ROBUSTNESS: MEDIUM — depends on whether the site uses Redux/Vuex global state.")
    else:
        print("  No window global state variables found.")

    # ================================================================== #
    # APPROACH 3: Network API calls
    # ================================================================== #
    print("\n" + "=" * 70)
    print("APPROACH 3: Network API / GraphQL calls")
    print("=" * 70)

    # Also look for fetch/XHR patterns in the HTML source
    api_patterns = re.findall(
        r'(?:fetch|axios\.get|axios\.post|XMLHttpRequest)[^"\']*["\']([^"\']*(?:api|graphql|product)[^"\']*)["\']',
        html_to_search,
    )

    if network_api_calls:
        print(f"  Captured {len(network_api_calls)} API/product network call(s) during page load:")
        for call in network_api_calls[:5]:
            print(f"\n  URL: {call['url']}")
            print(f"  Status: {call.get('status')}, Size: {call.get('body_size', 0):,} bytes")
            if "body_json" in call:
                inci_hits = find_inci_in_json(call["body_json"])
                if inci_hits:
                    print("  INCI FOUND in this API response!")
                    for path, sample in inci_hits[:3]:
                        print(f"    {path}: {sample[:400]}")
                else:
                    print("  No INCI-like content (JSON keys preview):")
                    if isinstance(call["body_json"], dict):
                        print(f"    {list(call['body_json'].keys())[:8]}")
            elif "body_text" in call:
                print(f"  Body preview: {call['body_text'][:200]}")
        print("\n  ROBUSTNESS: HIGH if a stable API endpoint exists (e.g. REST/GraphQL).")
        print("  HOW TO EXTRACT: Replay the API call with httpx, parse JSON response.")
    else:
        print("  No API/product network calls captured during page load.")

    if api_patterns:
        print(f"  Found {len(api_patterns)} API URL patterns in HTML source:")
        for p in api_patterns[:5]:
            print(f"    {p}")

    # Also scan raw HTML for any /api/ or /graphql endpoints
    api_urls_in_source = set(re.findall(r'["\'](/(?:api|graphql|_next/data)[^"\']+)["\']', html_to_search))
    if api_urls_in_source:
        print(f"\n  API-like URLs found in HTML source ({len(api_urls_in_source)} unique):")
        for u in sorted(api_urls_in_source)[:10]:
            print(f"    {u}")

    # ================================================================== #
    # APPROACH 4: Raw HTML text search for INCI content
    # ================================================================== #
    print("\n" + "=" * 70)
    print("APPROACH 4: Raw HTML text scan for INCI ingredient text")
    print("=" * 70)

    # Search for ingredient-like text blocks in the HTML
    # Pattern: text containing multiple INCI names separated by commas
    inci_block_patterns = [
        # Look for text nodes that are long comma-separated lists with INCI words
        r'(?:Ingredients?|INCI|Composition)[:\s]*([A-Za-z][^<]{50,})',
        # Common INCI starters
        r'(?:Aqua|Water)[^<,]{0,20}(?:,\s*[A-Z][a-z][^,<]{2,30}){5,}',
        # data-* attributes containing ingredient-like text
        r'data-[^=]+=\s*["\']([^"\']*(?:aqua|water|glycerin)[^"\']*)["\']',
    ]

    found_inci_raw = []
    for pat in inci_block_patterns:
        matches = re.findall(pat, html_to_search, re.IGNORECASE)
        for m in matches:
            if looks_like_inci(m):
                found_inci_raw.append(m.strip())

    # Also look for any text node that has 5+ consecutive INCI-like words
    # by scanning all text between tags
    text_nodes = re.findall(r'>([^<]{80,})<', html_to_search)
    for node in text_nodes:
        if looks_like_inci(node):
            found_inci_raw.append(node.strip())

    # Deduplicate
    seen = set()
    unique_inci = []
    for item in found_inci_raw:
        key = item[:50]
        if key not in seen:
            seen.add(key)
            unique_inci.append(item)

    if unique_inci:
        print(f"  Found {len(unique_inci)} INCI-like text block(s) in raw HTML!")
        for i, block in enumerate(unique_inci[:5]):
            print(f"\n  Block {i+1}:")
            print(f"    {block[:500]}")

        # Check if they have stable parent attributes
        for block_text in unique_inci[:3]:
            escaped = re.escape(block_text[:40])
            # Find what element wraps this text
            context_match = re.search(
                rf'(<[^>]+>)\s*{escaped}',
                html_to_search,
                re.IGNORECASE,
            )
            if context_match:
                tag = context_match.group(1)
                print(f"\n  Wrapping tag: {tag[:200]}")
                # Check for stable attributes
                has_data = bool(re.search(r'data-[a-z]', tag))
                has_id = bool(re.search(r'\bid=', tag))
                has_aria = bool(re.search(r'aria-', tag))
                print(f"  Stable selectors: data-*={has_data}, id={has_id}, aria-*={has_aria}")

        print("\n  ROBUSTNESS: MEDIUM — text is stable but parent element class names may shift.")
        print("  HOW TO EXTRACT: Use regex on rendered HTML or DOM traversal via Playwright.")
        print("  Playwright approach: page.locator('text=Aqua').locator('..').text_content()")
    else:
        print("  No INCI-like text blocks found in raw/rendered HTML.")
        print("  This likely means the ingredient text is loaded via a secondary JS/API call.")

    # ================================================================== #
    # APPROACH 5: LLM pattern extraction hint
    # ================================================================== #
    print("\n" + "=" * 70)
    print("APPROACH 5: LLM-based extraction from raw HTML")
    print("=" * 70)

    # Sample a window of HTML around any keyword match
    for keyword in ["Ingredient", "INCI", "Aqua", "Water"]:
        pos = html_to_search.lower().find(keyword.lower())
        if pos != -1:
            window = html_to_search[max(0, pos - 100):pos + 800]
            # Strip most tags for readability
            clean = re.sub(r'<[^>]+>', ' ', window)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if len(clean) > 50:
                print(f"\n  Found keyword '{keyword}' at position {pos:,}")
                print(f"  Surrounding text (stripped tags):\n    {clean[:600]}")
                break

    print("""
  HOW TO USE LLM EXTRACTION:
    1. Fetch the rendered HTML via Playwright.
    2. Strip all HTML tags with BeautifulSoup or regex to get plain text.
    3. Find the 2000-char window around "Ingredient" keyword.
    4. Send that window to Claude with prompt:
       "Extract the INCI ingredient list from this text. Return as a
        comma-separated list of ingredient names, one per line."
    5. This works even when the surrounding structure changes.

  ROBUSTNESS: HIGH for ingredient extraction, LOW for automation at scale
  (API cost, latency). Best as a fallback or one-time extraction.
""")

    # ================================================================== #
    # SUMMARY
    # ================================================================== #
    print("=" * 70)
    print("SUMMARY & RECOMMENDATION")
    print("=" * 70)

    approaches = {
        "1 __NEXT_DATA__": next_data_match is not None,
        "2 Window globals": bool(found_globals),
        "3 Network API calls": bool(network_api_calls),
        "4 Raw HTML text scan": bool(unique_inci),
        "5 LLM extraction": True,  # always feasible
    }

    for name, worked in approaches.items():
        status = "VIABLE" if worked else "NOT VIABLE / not found"
        print(f"  Approach {name}: {status}")


if __name__ == "__main__":
    asyncio.run(run_investigation())
