import asyncio
from playwright.async_api import async_playwright

# Selectors to try for product titles
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

# Selectors to try for "Load More" buttons
LOAD_MORE_SELECTORS = [
    "button:has-text('Load more')",
    "button:has-text('load more')",
    "button:has-text('Load More')",
    "button:has-text('Show more')",
    "button:has-text('Show More')",
    "button:has-text('View more')",
    "button:has-text('View More')",
    "a:has-text('Load more')",
    "a:has-text('Show more')",
    "a:has-text('View more')",
    "[class*='load-more']",
    "[class*='loadmore']",
    "[class*='show-more']",
    "[id*='load-more']",
    "[data-action='load-more']",
]


async def find_load_more_button(page):
    """Return the first visible Load More button element, or None."""
    for sel in LOAD_MORE_SELECTORS:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    return el, sel
        except Exception:
            continue
    return None, None


async def scroll_and_wait(page):
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)


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
        # Give JS-rendered products time to appear
        await asyncio.sleep(5)

        print(f"Page title: {await page.title()}")
        print(f"URL: {page.url}")

        # ── Click "Load More" repeatedly ──────────────────────────────────────
        load_more_clicked = 0
        load_more_selector_used = None
        click_round = 0

        while True:
            click_round += 1

            # Scroll to bottom first so the Load More button becomes visible
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            btn, sel = await find_load_more_button(page)
            if btn is None:
                print(f"\n[Round {click_round}] No Load More button visible -- stopping.")
                break

            load_more_selector_used = sel
            print(f"[Round {click_round}] Found Load More button via '{sel}' -- clicking...")
            try:
                await btn.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)

                # Use page.click with the selector directly for reliability
                await page.click(sel, timeout=5000)
                load_more_clicked += 1
                print(f"  Clicked successfully. Waiting for new products to render...")
                # Wait for new products to render
                await asyncio.sleep(4)
                # Scroll down to load lazy images and see new content
                await scroll_and_wait(page)
            except Exception as e:
                print(f"  page.click failed ({e}), trying btn.click...")
                try:
                    await btn.click()
                    load_more_clicked += 1
                    await asyncio.sleep(4)
                    await scroll_and_wait(page)
                except Exception as e2:
                    print(f"  btn.click also failed: {e2}. Stopping Load More loop.")
                    break

        # Final scroll pass to make sure lazy-loaded items appear
        print("\nFinal scroll pass...")
        prev_height = -1
        for _ in range(10):
            height = await page.evaluate("document.body.scrollHeight")
            if height == prev_height:
                break
            prev_height = height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

        # ── Try every title selector, record raw hits ─────────────────────────
        print("\n=== SELECTOR PROBE ===")
        selector_results = {}
        for sel in TITLE_SELECTORS:
            try:
                els = await page.query_selector_all(sel)
                names = [await el.inner_text() for el in els]
                names = [n.strip() for n in names if n.strip()]
                selector_results[sel] = names
                print(f"  {sel!r:50s}  -> {len(names)} raw hits")
            except Exception as e:
                print(f"  {sel!r:50s}  -> ERROR: {e}")

        # ── Pick best selector (most raw hits) ────────────────────────────────
        best_sel = max(selector_results, key=lambda s: len(selector_results[s]), default=None)
        best_names = selector_results.get(best_sel, [])

        # Deduplicate preserving order
        seen = set()
        unique_names = []
        for name in best_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        # ── Summary ───────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        if load_more_clicked:
            print(f"Load More button found:   YES -- selector: {load_more_selector_used!r}")
        else:
            print("Load More button found:   NO")
        print(f"Load More clicks made:    {load_more_clicked}")
        print(f"Best title selector:      {best_sel!r}")
        print(f"Raw element count:        {len(best_names)}")
        print(f"Deduplicated count:       {len(unique_names)}")
        print("\n=== ALL UNIQUE PRODUCT NAMES ===")
        for i, name in enumerate(unique_names, 1):
            print(f"{i:3d}. {name}")

        await browser.close()


asyncio.run(main())
