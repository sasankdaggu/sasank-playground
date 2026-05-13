import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            "https://aqualogica.in/collections/routine-sun-protection",
            wait_until="domcontentloaded",
            timeout=60000
        )
        await asyncio.sleep(4)

        # Scroll to bottom repeatedly until no new content loads
        prev_height = 0
        for i in range(30):
            height = await page.evaluate("document.body.scrollHeight")
            if height == prev_height:
                break
            prev_height = height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

        # Extract all product titles using the confirmed selector
        elements = await page.query_selector_all(".hdt-card-product__title")
        all_names = [await el.inner_text() for el in elements]
        all_names = [n.strip() for n in all_names if n.strip()]

        # Deduplicate while preserving order
        seen = set()
        unique_names = []
        for name in all_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        print(f"\nPage: {await page.title()}")
        print(f"URL: {page.url}")
        print(f"\nTotal .hdt-card-product__title elements: {len(all_names)}")
        print(f"DISTINCT product names: {len(unique_names)}")
        print("\n=== ALL DISTINCT PRODUCT NAMES ===")
        for i, name in enumerate(unique_names, 1):
            print(f"{i:2d}. {name}")

        await browser.close()

asyncio.run(main())
