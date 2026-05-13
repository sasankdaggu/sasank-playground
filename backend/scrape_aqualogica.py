import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://aqualogica.in/collections/routine-sun-protection", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        # Scroll to bottom repeatedly until no new content loads
        prev_height = 0
        for i in range(30):
            height = await page.evaluate("document.body.scrollHeight")
            if height == prev_height:
                print(f"No new content after scroll {i}, stopping.")
                break
            prev_height = height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

        # Also dump page title and URL to confirm we're on the right page
        print(f"\nPage title: {await page.title()}")
        print(f"URL: {page.url}")

        # Strategy: extract distinct product links (/products/ hrefs) and their text
        print("\nDumping anchor hrefs containing '/products/':")
        links = await page.query_selector_all("a[href*='/products/']")
        seen_hrefs = set()
        products = []
        for link in links:
            href = await link.get_attribute("href")
            text = (await link.inner_text()).strip()
            if href and href not in seen_hrefs:
                seen_hrefs.add(href)
                if text:
                    products.append((text, href))
                    print(f"  [{text}] -> {href}")

        print(f"\nTotal distinct product links: {len(seen_hrefs)}")
        print(f"Total with non-empty text: {len(products)}")

        # Also dump h2/h3/h4 for reference
        print("\nAll h3 tags on the page:")
        for tag in ["h3", "h4"]:
            elements = await page.query_selector_all(tag)
            if elements:
                texts = [await el.inner_text() for el in elements]
                texts = [t.strip() for t in texts if t.strip()]
                print(f"  {tag} ({len(texts)}): {texts}")

        # Try common Shopify selectors more broadly
        print("\nTrying broad Shopify selectors:")
        for selector in [
            ".product-card__title", ".card__heading", ".product-item__title",
            ".product__title", "h2.h3", ".grid-view-item__title",
            "a.full-unstyled-link", ".product-card a span",
            ".card__information a", "h3.card__heading",
            "[class*='product-card__name']", "[class*='product__name']",
            "[class*='ProductCard__title']", "[class*='product_title']",
            ".product-loop__title", ".product-loop a",
        ]:
            elements = await page.query_selector_all(selector)
            if elements:
                names = [await el.inner_text() for el in elements]
                names = [n.strip() for n in names if n.strip()]
                if names:
                    print(f"  Selector '{selector}': {names}")

        await browser.close()

asyncio.run(main())
