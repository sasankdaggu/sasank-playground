import asyncio
import re
from playwright.async_api import async_playwright

TITLE_SELECTORS = [
    ".hdt-card-product__title",
    ".card-product__title",
    ".product-card__title",
    ".product__title",
    "[class*='product'][class*='title']",
    "h2.card__heading a",
    ".card__heading",
    "h3.card-information__text",
    ".card-information__text",
    "a.full-unstyled-link",
]

LOAD_MORE_SELECTORS = [
    "a:has-text('Load more')",
    "button:has-text('Load more')",
    "button:has-text('load more')",
    "button:has-text('Load More')",
    "button:has-text('Show more')",
    "button:has-text('Show More')",
    "button:has-text('View more')",
    "button:has-text('View More')",
    "a:has-text('Show more')",
    "a:has-text('View more')",
    "[class*='load-more']",
    "[class*='loadmore']",
    "[class*='show-more']",
    "[id*='load-more']",
    "[data-action='load-more']",
]


def categorize(name: str) -> tuple[int, str]:
    """
    Returns (bucket_number, reason).
    1 = True individual single SKU
    2 = Multi-unit pack of same product (Pack of 2, Pack of 3, etc.)
    3 = Multi-product combo/bundle (Combo, Duo, Trio, Kit, BFFs, Bundle, Set, etc.)
    """
    n = name.lower()

    # Bucket 3: multi-product combos/bundles
    # NOTE: "+" in brand names like "Glow+" is NOT a separator — exclude those
    # We only treat " + " (space-plus-space) as a product separator.
    # "Makeup-Set" is a hyphenated adjective (makeup-setting), NOT a bundle —
    # so we require "set" to be a standalone word NOT preceded by a hyphen.
    # "Pair" (as in "Barrier Boosting Pair") means two different products.
    combo_keywords = [
        r"\bcombo\b",
        r"\bduo\b",
        r"\btrio\b",
        r"\bkit\b",
        r"\bbff\b",
        r"\bbffs\b",
        r"\bbundle\b",
        r"\bpair\b",
        # "set" only as standalone word not preceded by hyphen (excludes "makeup-set")
        r"(?<![-\w])set\b",
        r"\bcollection\b",
        r" \+ ",   # space-plus-space = two distinct products joined
    ]
    for kw in combo_keywords:
        if re.search(kw, n):
            return 3, f"combo keyword: {kw}"

    # Bucket 2: multi-unit packs of the SAME product
    pack_keywords = [
        r"\bpack of \d+\b",
        r"\bpack of two\b",
        r"\bpack of three\b",
        r"\b2[ -]?pack\b",
        r"\b3[ -]?pack\b",
        r"\btwin pack\b",
        r"\bdouble pack\b",
        r"\bvalue pack\b",
        r"\bbuy \d+ get\b",
        r"\bx2\b",
        r"\bx3\b",
    ]
    for kw in pack_keywords:
        if re.search(kw, n):
            return 2, f"pack keyword: {kw}"

    # Bucket 1: true individual single SKU
    return 1, "individual SKU"


async def find_load_more_button(page):
    for sel in LOAD_MORE_SELECTORS:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    return el, sel
        except Exception:
            continue
    return None, None


async def count_products(page, selector):
    try:
        els = await page.query_selector_all(selector)
        return len(els)
    except Exception:
        return 0


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        print("Loading page...")
        await page.goto(
            "https://aqualogica.in/collections/routine-sun-protection",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await asyncio.sleep(6)

        print(f"Page title: {await page.title()}")

        best_sel = ".hdt-card-product__title"  # known working selector

        # Click Load More repeatedly until it disappears
        load_more_clicked = 0
        click_round = 0
        max_rounds = 20  # safety cap

        while click_round < max_rounds:
            click_round += 1

            # Scroll to bottom to reveal the Load More button
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

            current_count = await count_products(page, best_sel)
            print(f"[Round {click_round}] Products visible so far: {current_count}")

            btn, sel = await find_load_more_button(page)
            if btn is None:
                print(f"  No Load More button visible — stopping.")
                break

            print(f"  Found Load More via '{sel}' — clicking via JS...")
            try:
                # JS click bypasses stale element issues
                await page.evaluate("(el) => el.click()", btn)
                load_more_clicked += 1
                print(f"  Clicked (total clicks: {load_more_clicked}). Waiting for products to load...")
                await asyncio.sleep(6)
                new_count = await count_products(page, best_sel)
                print(f"  Products after click: {new_count}")
                if new_count == current_count:
                    print("  Count didn't increase — may be done, trying one more scroll...")
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(3)
                    new_count2 = await count_products(page, best_sel)
                    if new_count2 == current_count:
                        print("  Still same count — stopping.")
                        break
            except Exception as e:
                print(f"  JS click failed: {e}. Trying Playwright click...")
                try:
                    await page.locator(sel).first.click(timeout=5000)
                    load_more_clicked += 1
                    await asyncio.sleep(6)
                except Exception as e2:
                    print(f"  Playwright click also failed: {e2}. Stopping.")
                    break

        # Final scroll to load any lazy images / remaining items
        print("\nFinal scroll pass...")
        prev_height = -1
        for _ in range(15):
            height = await page.evaluate("document.body.scrollHeight")
            if height == prev_height:
                break
            prev_height = height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

        # Try all selectors to find best one
        selector_results = {}
        for sel in TITLE_SELECTORS:
            try:
                els = await page.query_selector_all(sel)
                names = [await el.inner_text() for el in els]
                names = [n.strip() for n in names if n.strip()]
                selector_results[sel] = names
                print(f"  {sel!r:50s}  -> {len(names)} hits")
            except Exception as e:
                selector_results[sel] = []

        best_sel = max(selector_results, key=lambda s: len(selector_results[s]), default=None)
        best_names = selector_results.get(best_sel, [])

        # Deduplicate preserving order
        seen = set()
        unique_names = []
        for name in best_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        await browser.close()

    # ── Categorization ──────────────────────────────────────────────────────
    bucket1, bucket2, bucket3 = [], [], []
    all_products = []

    for name in unique_names:
        bucket_num, reason = categorize(name)
        all_products.append((name, bucket_num, reason))
        if bucket_num == 1:
            bucket1.append(name)
        elif bucket_num == 2:
            bucket2.append(name)
        else:
            bucket3.append(name)

    print("\n" + "=" * 72)
    print("FULL PRODUCT LIST WITH BUCKET ASSIGNMENTS")
    print("Bucket 1 = Individual SKU | Bucket 2 = Multi-unit Pack | Bucket 3 = Combo/Bundle")
    print("=" * 72)
    print(f"{'#':>3}  {'B':>2}  PRODUCT NAME")
    print("-" * 72)
    for i, (name, bucket_num, reason) in enumerate(all_products, 1):
        print(f"{i:3d}  {bucket_num:>2}  {name}")

    print("\n" + "=" * 72)
    print("BUCKET COUNTS")
    print("=" * 72)
    print(f"  Bucket 1 — True individual single SKU:         {len(bucket1):3d}")
    print(f"  Bucket 2 — Multi-unit pack of same product:    {len(bucket2):3d}")
    print(f"  Bucket 3 — Multi-product combo/bundle:         {len(bucket3):3d}")
    print(f"  TOTAL scraped & categorized:                   {len(all_products):3d}")

    print("\n" + "=" * 72)
    print("BUCKET 1 — TRUE INDIVIDUAL SINGLE SKUs")
    print("=" * 72)
    for i, name in enumerate(bucket1, 1):
        print(f"{i:3d}. {name}")

    print("\n" + "=" * 72)
    print("BUCKET 2 — MULTI-UNIT PACKS OF SAME PRODUCT")
    print("=" * 72)
    for i, name in enumerate(bucket2, 1):
        print(f"{i:3d}. {name}")

    print("\n" + "=" * 72)
    print("BUCKET 3 — MULTI-PRODUCT COMBOS / BUNDLES")
    print("=" * 72)
    for i, name in enumerate(bucket3, 1):
        print(f"{i:3d}. {name}")

    print(f"\n--- Load More clicks: {load_more_clicked} | Best selector: {best_sel!r} | Total unique: {len(unique_names)} ---")


asyncio.run(main())
