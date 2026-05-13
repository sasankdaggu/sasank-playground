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
                print(f"No new content after scroll {i}, stopping.")
                break
            prev_height = height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

        print(f"\nPage title: {await page.title()}")
        print(f"URL: {page.url}")

        # Get the full HTML of the first product card to understand structure
        first_card = await page.query_selector(".hdt-card-product, [class*='card-product'], [class*='CardProduct']")
        if first_card:
            html = await first_card.inner_html()
            print("First card HTML (3000 chars):")
            print(html[:3000])
        else:
            # Try to get a bigger parent from the first product link
            first_link = await page.query_selector("a[href*='/products/']")
            if first_link:
                # Get grandparent HTML
                parent_html = await page.evaluate("""(el) => {
                    let node = el.parentElement;
                    while (node && node.parentElement) {
                        if (node.className && typeof node.className === 'string' &&
                            (node.className.includes('hdt') || node.className.includes('product') || node.className.includes('card'))) {
                            return { cls: node.className, html: node.outerHTML.substring(0, 5000) };
                        }
                        node = node.parentElement;
                    }
                    return null;
                }""", first_link)
                if parent_html:
                    print(f"Container class: {parent_html['cls']}")
                    print(f"Container HTML:\n{parent_html['html']}")

        # Try hdt-specific selectors based on the card HTML we saw
        print("\n\n--- Trying hdt selectors ---")
        for selector in [
            ".hdt-card-product__title",
            ".hdt-card-product [class*='title']",
            "[class*='hdt-card-product'] p",
            "[class*='card-product__name']",
            "[class*='card-product__title']",
            ".hdt-card-product__info [class*='title']",
            ".hdt-card-product__info p",
            ".hdt-card-product__info a",
            ".hdt-card-product a[href*='/products/'][class*='title']",
            ".hdt-card-product__content p",
            ".hdt-card-product__content a",
        ]:
            elements = await page.query_selector_all(selector)
            if elements:
                names = [await el.inner_text() for el in elements]
                names = [n.strip() for n in names if n.strip()]
                if names:
                    print(f"  Selector '{selector}' ({len(names)}): {names[:5]}...")

        # Dump all classes that have "title" or "name" in them within product cards
        print("\n--- JS extraction: all elements with 'title'/'name' class inside product cards ---")
        result = await page.evaluate("""() => {
            const cards = document.querySelectorAll('[class*="card-product"], [class*="CardProduct"], [class*="product-card"]');
            const seen = new Set();
            const items = [];
            cards.forEach(card => {
                const els = card.querySelectorAll('*');
                els.forEach(el => {
                    const cls = el.className;
                    if (typeof cls === 'string' && (cls.includes('title') || cls.includes('name') || cls.includes('heading'))) {
                        const text = el.innerText.trim();
                        if (text && !seen.has(cls)) {
                            seen.add(cls);
                            items.push({cls: cls, text: text.substring(0, 100)});
                        }
                    }
                });
            });
            return items;
        }""")
        for item in result:
            print(f"  class='{item['cls']}': {repr(item['text'])}")

        # Final approach: get all product cards and extract title text directly
        print("\n--- JS extraction: all product titles from cards ---")
        titles = await page.evaluate("""() => {
            // Look for all product card containers
            const cards = document.querySelectorAll('[class*="hdt-card-product"], [class*="card-product"]');
            const results = [];
            cards.forEach(card => {
                // Get all links with /products/ in href
                const links = card.querySelectorAll('a[href*="/products/"]');
                links.forEach(link => {
                    // Check link's aria-label or title attribute
                    const ariaLabel = link.getAttribute('aria-label');
                    const titleAttr = link.getAttribute('title');
                    const href = link.getAttribute('href');
                    if (ariaLabel || titleAttr) {
                        results.push({
                            type: 'link-attr',
                            text: ariaLabel || titleAttr,
                            href: href
                        });
                    }
                });
                // Look for any element that has a product name pattern
                const allText = card.querySelectorAll('p, span, a');
                allText.forEach(el => {
                    const cls = el.className || '';
                    if (typeof cls === 'string' && (cls.includes('title') || cls.includes('name'))) {
                        const text = el.innerText.trim();
                        if (text) {
                            results.push({type: 'class-match', cls: cls, text: text.substring(0, 150)});
                        }
                    }
                });
            });
            return results;
        }""")
        for item in titles:
            print(f"  {item}")

        await browser.close()

asyncio.run(main())
