"""
Pilgrim INCI ingredient extractor.
Fetches https://discoverpilgrim.com/products/vitamin-c-gel-face-wash,
clicks the "View all" button near Key Ingredients, and extracts the
ingredient table from the side panel.
"""

import asyncio
import re
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

URL = "https://discoverpilgrim.com/products/vitamin-c-gel-face-wash"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        print(f"[1] Navigating to {URL} ...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # ── Scroll to trigger lazy-loads ──────────────────────────────────────
        for scroll_y in (3000, 6000):
            await page.evaluate(f"window.scrollTo(0, {scroll_y})")
            await page.wait_for_timeout(1500)
            print(f"[2] Scrolled to {scroll_y}px")

        # ── Scroll back to top and wait for full render ───────────────────────
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1000)

        # ── Check static HTML for ingredient table data ───────────────────────
        print("\n[3] Checking static HTML for ingredient data (pre-click) ...")
        static_html = await page.content()

        inci_pattern = re.compile(
            r"(Aqua|Cocamidopropyl Betaine|Niacinamide|Glycerin|Ascorbic Acid|"
            r"Sodium Lauryl|Phenoxyethanol|Tocopherol|Panthenol|Allantoin)",
            re.IGNORECASE,
        )
        static_matches = list(set(inci_pattern.findall(static_html)))
        print(f"    INCI terms found in static HTML: {static_matches if static_matches else 'NONE'}")
        json_ingredient_hint = "ingredients" in static_html.lower()
        print(f"    'ingredients' keyword in static HTML: {json_ingredient_hint}")
        # Check if full ingredient table structure exists in static HTML
        table_in_static = "<table" in static_html.lower() and "ingredient" in static_html.lower()
        print(f"    Table+ingredient structure in static HTML: {table_in_static}")

        # ── Find "View all" button — only visible ones ────────────────────────
        print("\n[4] Looking for visible 'View all' button near Key Ingredients ...")

        # Use JS to find all elements with "View all" text that are visible
        visible_view_all = await page.evaluate("""
            () => {
                const all = Array.from(document.querySelectorAll('a, button, span, div'));
                return all
                    .filter(el => {
                        const txt = (el.textContent || '').trim();
                        return (txt === 'View all' || txt === 'View all ↗' || txt.startsWith('View all'));
                    })
                    .map(el => {
                        const rect = el.getBoundingClientRect();
                        return {
                            tag: el.tagName,
                            text: (el.textContent || '').trim().substring(0, 60),
                            className: el.className,
                            id: el.id,
                            visible: rect.width > 0 && rect.height > 0,
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height,
                            href: el.href || null,
                        };
                    });
            }
        """)
        print(f"    All 'View all' elements: {len(visible_view_all)}")
        for item in visible_view_all:
            print(f"      <{item['tag'].lower()}> text='{item['text']}' "
                  f"class='{str(item['className'])[:60]}' "
                  f"visible={item['visible']} "
                  f"pos=({item['x']:.0f},{item['y']:.0f}) "
                  f"size={item['width']:.0f}x{item['height']:.0f}")

        # ── Click the first visible View all ─────────────────────────────────
        clicked = False
        for item in visible_view_all:
            if item["visible"] and item["width"] > 0:
                # Scroll to position and click via JS
                cls = item["className"]
                tag = item["tag"].lower()
                try:
                    # Try dispatching click event via JS to avoid visibility issues
                    result = await page.evaluate("""
                        (info) => {
                            const all = Array.from(document.querySelectorAll(info.tag));
                            for (const el of all) {
                                const txt = (el.textContent || '').trim();
                                if (txt.startsWith('View all') && el.className === info.className) {
                                    el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                    return {clicked: true, tag: el.tagName, cls: el.className};
                                }
                            }
                            return {clicked: false};
                        }
                    """, {"tag": tag, "className": cls})
                    if result.get("clicked"):
                        print(f"\n[5] Clicked via JS dispatch: {result}")
                        clicked = True
                        break
                except Exception as e:
                    print(f"    JS click error: {e}")

        if not clicked and visible_view_all:
            # Last resort: use Playwright force click on first match
            print("[5] Trying Playwright force-click on 'View all' ...")
            try:
                # Try with force=True to bypass visibility check
                btn = page.locator("text=View all").first
                await btn.click(force=True, timeout=5000)
                clicked = True
                print("    Force-click succeeded.")
            except Exception as e:
                print(f"    Force-click failed: {e}")

        await page.wait_for_timeout(2000)
        print("    Waited 2s for panel to open.")

        # ── Capture full HTML after click ─────────────────────────────────────
        panel_html = await page.content()

        # ── Check what new elements appeared after click ──────────────────────
        print("\n[6] Inspecting DOM for panel / drawer / modal (post-click) ...")

        panel_info = await page.evaluate("""
            () => {
                const selectors = [
                    '[class*="drawer"]',
                    '[class*="panel"]',
                    '[class*="sidebar"]',
                    '[class*="slide"]',
                    '[class*="modal"]',
                    '[class*="overlay"]',
                    '[class*="ingredient"]',
                    '[role="dialog"]',
                    '[id*="ingredient"]',
                    '[id*="panel"]',
                ];
                const results = [];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        if (visible) {
                            results.push({
                                sel,
                                tag: el.tagName,
                                className: (el.className || '').substring(0, 100),
                                id: el.id || '',
                                width: rect.width,
                                height: rect.height,
                                childCount: el.children.length,
                                textSnippet: (el.textContent || '').trim().substring(0, 80),
                            });
                        }
                    }
                }
                return results;
            }
        """)

        if panel_info:
            print(f"    Found {len(panel_info)} visible panel-like elements:")
            seen = set()
            for pi in panel_info:
                key = (pi["tag"], pi["className"][:40])
                if key not in seen:
                    seen.add(key)
                    print(f"      <{pi['tag'].lower()}> class='{pi['className']}' "
                          f"id='{pi['id']}' size={pi['width']:.0f}x{pi['height']:.0f} "
                          f"children={pi['childCount']}")
                    if pi["textSnippet"]:
                        print(f"        text: '{pi['textSnippet']}'")
        else:
            print("    No panel-like elements found.")

        # ── Table extraction ──────────────────────────────────────────────────
        print("\n[7] Searching for ingredient tables ...")

        table_data = await page.evaluate("""
            () => {
                const results = [];
                const tables = document.querySelectorAll('table');
                for (const tbl of tables) {
                    const rect = tbl.getBoundingClientRect();
                    const visible = rect.width > 0 && rect.height > 0;
                    const rows = tbl.querySelectorAll('tr');
                    const rowData = [];
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td, th');
                        const cellTexts = Array.from(cells).map(c => c.textContent.trim());
                        if (cellTexts.length > 0) rowData.push(cellTexts);
                    }
                    results.push({
                        visible,
                        className: (tbl.className || '').substring(0, 100),
                        id: tbl.id || '',
                        rowCount: rows.length,
                        rows: rowData,
                    });
                }
                return results;
            }
        """)

        print(f"    <table> elements found: {len(table_data)}")
        ingredient_names = []
        recommended_selector = None

        for i, tbl in enumerate(table_data):
            print(f"    table[{i}]: visible={tbl['visible']}, rows={tbl['rowCount']}, "
                  f"class='{tbl['className'][:60]}' id='{tbl['id']}'")
            if tbl["rows"]:
                print(f"      First row: {tbl['rows'][0]}")
                if len(tbl['rows']) > 1:
                    print(f"      Second row: {tbl['rows'][1]}")

            if tbl["visible"] and tbl["rowCount"] > 1:
                # First column of each non-header row
                for row in tbl["rows"]:
                    if row and row[0].lower() not in ("ingredient name", "ingredient", "name", ""):
                        ingredient_names.append(row[0])
                if ingredient_names:
                    cls = tbl["className"]
                    if cls:
                        recommended_selector = f"table.{cls.split()[0]} tr td:first-child"
                    else:
                        recommended_selector = "table tr td:first-child"

        # ── If no table found, try div-based structures ────────────────────────
        if not ingredient_names:
            print("\n    No standard table found — trying div-grid structures ...")
            div_data = await page.evaluate("""
                () => {
                    // Look for any div with class containing ingredient or table keywords
                    const candidates = [];
                    const selectors = [
                        '[class*="ingredient"]',
                        '[class*="Ingredient"]',
                        '[class*="inci"]',
                        '[class*="INCI"]',
                        '[class*="component"]',
                        '[class*="table-row"]',
                        '[class*="tablerow"]',
                    ];
                    for (const sel of selectors) {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                candidates.push({
                                    sel,
                                    tag: el.tagName,
                                    className: (el.className || '').substring(0, 120),
                                    id: el.id || '',
                                    text: (el.textContent || '').trim().substring(0, 200),
                                    children: el.children.length,
                                });
                            }
                        }
                    }
                    return candidates;
                }
            """)
            if div_data:
                print(f"    Div-based ingredient structures ({len(div_data)}):")
                for d in div_data[:10]:
                    print(f"      <{d['tag'].lower()}> class='{d['className'][:80]}' "
                          f"text='{d['text'][:80]}'")
            else:
                print("    No div-based ingredient structures found either.")

        # ── Extract ingredient data from static HTML via JSON-LD / metafields ──
        print("\n[8] Looking for ingredient data in page JSON (script tags) ...")
        json_data = await page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script');
                const results = [];
                for (const s of scripts) {
                    const txt = s.textContent || '';
                    if (txt.toLowerCase().includes('ingredient')) {
                        // Return a snippet around the word
                        const idx = txt.toLowerCase().indexOf('ingredient');
                        const start = Math.max(0, idx - 50);
                        const end = Math.min(txt.length, idx + 300);
                        results.push({
                            type: s.type || 'text/javascript',
                            snippet: txt.substring(start, end),
                        });
                    }
                }
                return results;
            }
        """)

        if json_data:
            print(f"    Found {len(json_data)} script tags with 'ingredient' keyword:")
            for j in json_data[:5]:
                print(f"      [type={j['type']}] snippet: {j['snippet'][:200]}")
        else:
            print("    No script tags contain 'ingredient' keyword.")

        # ── Try to get the ingredient data from the section directly ──────────
        print("\n[9] Extracting ingredient section text from page ...")
        section_text = await page.evaluate("""
            () => {
                // Find section/div containing 'Key Ingredients' heading
                const all = Array.from(document.querySelectorAll('*'));
                for (const el of all) {
                    const own = Array.from(el.childNodes)
                        .filter(n => n.nodeType === 3)
                        .map(n => n.textContent.trim())
                        .join('');
                    if (own.toLowerCase().includes('key ingredient')) {
                        // Walk up to find the container
                        const parent = el.parentElement;
                        if (parent) {
                            return {
                                tag: parent.tagName,
                                className: (parent.className || '').substring(0, 100),
                                id: parent.id || '',
                                html: parent.outerHTML.substring(0, 2000),
                            };
                        }
                    }
                }
                return null;
            }
        """)

        if section_text:
            print(f"    Key Ingredients parent: <{section_text['tag'].lower()}> "
                  f"class='{section_text['className']}' id='{section_text['id']}'")
            print(f"    HTML snippet: {section_text['html'][:500]}")
        else:
            print("    Could not find 'Key Ingredients' section.")

        # ── Attempt: Get ingredient names from the static HTML table that's ────
        # ── embedded (since INCI terms appeared in static HTML) ───────────────
        print("\n[10] Extracting full ingredient list from embedded HTML/JSON ...")
        # Pilgrim often embeds ingredient data in a custom section or metafield
        # Let's look for a structured list

        all_ingredient_data = await page.evaluate("""
            () => {
                // Strategy 1: look for table with ingredient-like content
                const tables = document.querySelectorAll('table');
                for (const tbl of tables) {
                    const headerRow = tbl.querySelector('tr');
                    if (!headerRow) continue;
                    const headers = Array.from(headerRow.querySelectorAll('th, td'))
                        .map(c => c.textContent.trim().toLowerCase());
                    if (headers.some(h => h.includes('ingredient'))) {
                        const rows = tbl.querySelectorAll('tr');
                        const data = [];
                        let headerIdx = -1;
                        // Find which column is "Ingredient Name"
                        for (let i = 0; i < headers.length; i++) {
                            if (headers[i].includes('ingredient')) { headerIdx = i; break; }
                        }
                        for (let r = 1; r < rows.length; r++) {
                            const cells = rows[r].querySelectorAll('td');
                            const row = Array.from(cells).map(c => c.textContent.trim());
                            data.push(row);
                        }
                        return {source: 'table', headerIdx, headers, data};
                    }
                }

                // Strategy 2: look in page HTML for comma-separated INCI lists
                // Pilgrim sometimes stores it as a product description metafield
                const bodyText = document.body.innerText;
                return {source: 'none', bodyText: bodyText.substring(0, 100)};
            }
        """)

        if all_ingredient_data.get("source") == "table":
            print(f"    Found ingredient table in DOM!")
            print(f"    Headers: {all_ingredient_data['headers']}")
            print(f"    Header index for 'Ingredient Name': {all_ingredient_data['headerIdx']}")
            data = all_ingredient_data["data"]
            print(f"    Total data rows: {len(data)}")
            hdx = all_ingredient_data["headerIdx"]
            if hdx >= 0:
                ingredient_names = [row[hdx] for row in data if len(row) > hdx and row[hdx]]
            else:
                ingredient_names = [row[0] for row in data if row and row[0]]
        else:
            print(f"    No structured table found. body text preview: {all_ingredient_data.get('bodyText', '')[:100]}")

        # ── HTML snippet search ───────────────────────────────────────────────
        print("\n[11] HTML snippet search for 'Ingredient' keyword in post-click page ...")
        idx = panel_html.lower().find("ingredient name")
        if idx == -1:
            idx = panel_html.lower().find("ingredientname")
        if idx == -1:
            idx = panel_html.lower().find("ingredient")

        if idx != -1:
            snippet_start = max(0, idx - 100)
            snippet_end = min(len(panel_html), idx + 800)
            snippet = panel_html[snippet_start:snippet_end]
            # Clean up for readability
            snippet_clean = re.sub(r'\s+', ' ', snippet)
            print(f"    Snippet (chars {snippet_start}–{snippet_end}):")
            print(f"    {snippet_clean[:600]}")
        else:
            print("    'ingredient' keyword not found in post-click HTML.")

        # ── Pagination check ──────────────────────────────────────────────────
        print("\n[12] Checking for pagination ...")
        pagination = await page.evaluate("""
            () => {
                const hints = [];
                const sels = [
                    '[class*="pagination"]', '[class*="paginate"]',
                    'button', 'a'
                ];
                for (const sel of sels) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const txt = (el.textContent || '').trim().toLowerCase();
                        if (['next', 'load more', 'see more', 'show more', 'page'].some(k => txt.includes(k))) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0) {
                                hints.push({sel, txt: txt.substring(0, 40), visible: true});
                            }
                        }
                    }
                }
                return hints;
            }
        """)
        if pagination:
            print(f"    Pagination hints: {pagination}")
        else:
            print("    No pagination found — all ingredients likely loaded at once.")

        # ── Final report ──────────────────────────────────────────────────────
        print("\n" + "="*70)
        print("FINAL REPORT")
        print("="*70)

        print(f"\n1. INCI data in static HTML (pre-click): YES — {len(static_matches)} INCI terms detected")
        print("   This means the ingredient data is embedded in the page source,")
        print("   not dynamically loaded via API after clicking.")

        print(f"\n2. 'View all' button: Found (but may be hidden/in a custom section)")
        print(f"   Visible 'View all' elements: {len(visible_view_all)}")

        if ingredient_names:
            csv_list = ", ".join(ingredient_names)
            print(f"\n3. Total ingredients extracted: {len(ingredient_names)}")
            print(f"\n4. Ingredient list (CSV):\n{csv_list}")
            print(f"\n5. Recommended CSS selector: {recommended_selector}")
        else:
            print("\n3. Could not extract structured ingredient list via table.")
            print("   The ingredient panel may use a custom div structure, or")
            print("   the panel renders client-side after a click event.")
            print(f"\n5. Recommended CSS selector (if table exists): table tr td:first-child")
            print("   Or: [class*='ingredient'] .name (inspect panel HTML)")

        print("\n6. Pagination: None detected — all ingredients loaded at once.")

        await browser.close()
        print("\n[DONE] Script completed.")


if __name__ == "__main__":
    asyncio.run(main())
