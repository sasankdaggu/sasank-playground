"""Seed confirmed-working ingredient schemas for brands where auto-detection fails.

Used for brands where the hardcoded extractor works but Playwright-based detection
can't extract the ingredient HTML (e.g. Dot & Key's deeply JS-rendered product page).

Run once, or re-run to refresh:
  python -m scraper.seed_known_schemas
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app.config import settings  # noqa: E402

log = structlog.get_logger()

# Ground-truth schemas for brands where detection fails but extractors are confirmed.
# selector is verified against real product pages; status is 'active'.
KNOWN_SCHEMAS: list[dict] = [
    {
        "brand_domain": "beminimalist.co",
        "brand_name": "Minimalist",
        "brand_url": "https://beminimalist.co",
        "platform": "shopify",
        "css_selector": "div.toggle__content span.metafield-multi_line_text_field",
        "requires_js": True,
        "js_action": "scroll to 3000px and 6000px",
        "notes": "Multiple span.metafield-multi_line_text_field spans exist across the page "
                 "(marketing blurbs for individual ingredients). Scoping to div.toggle__content "
                 "selects only the span inside the ingredient accordion, which has the full INCI.",
        "sample_url": "https://beminimalist.co/products/niacinamide-5-face-serum-10ml",
        "sample_inci_preview": "Water/Aqua, Niacinamide, Dimethyl Isosorbide, Avena Sativa (Oat) Kernel Extract",
        "confidence": 0.92,
        "status": "active",
    },
    {
        "brand_domain": "plumgoodness.com",
        "brand_name": "Plum Goodness",
        "brand_url": "https://plumgoodness.com",
        "platform": "shopify",
        "css_selector": "div.ingredient-hidden span.metafield-multi_line_text_field",
        "requires_js": True,
        "js_action": "scroll to 3000px and 6000px",
        "notes": "Old Shopify template: full INCI hidden in div.ingredient-hidden behind a "
                 "'View more' button. New template (2025+) products do not expose full INCI in "
                 "HTML — extraction returns None for those and they stay as no_inci_html.",
        "sample_url": "https://plumgoodness.com/products/1-salicylic-acid-serum",
        "sample_inci_preview": None,
        "confidence": 0.75,
        "status": "active",
    },
    {
        "brand_domain": "dotandkey.com",
        "brand_name": "Dot & Key",
        "brand_url": "https://www.dotandkey.com",
        "platform": "shopify",
        "css_selector": "div.opend-full-ingredients",
        "requires_js": True,
        "js_action": "click summary:has-text(\"INGREDIENTS\") to expand accordion",
        "notes": "INCI is JS-populated into div.opend-full-ingredients after clicking the "
                 "INGREDIENTS <details>/<summary> accordion. The generic ingredient click in "
                 "_fetch_playwright handles this automatically.",
        "sample_url": "https://www.dotandkey.com/products/strawberry-bright-niacinamide-gel-face-wash",
        "sample_inci_preview": "Aqua, Cocamidopropyl Betaine, Glycerin, Decyl Glucoside",
        "confidence": 0.93,
        "status": "active",
    },
    {
        "brand_domain": "mcaffeine.com",
        "brand_name": "mCaffeine",
        "brand_url": "https://www.mcaffeine.com",
        "platform": "shopify",
        "css_selector": None,
        "requires_js": False,
        "js_action": None,
        "notes": "mCaffeine's INCI list is only available as a product label image — "
                 "no machine-readable ingredient text exists in the HTML.",
        "sample_url": None,
        "sample_inci_preview": None,
        "confidence": 1.0,
        "status": "no_inci",
    },
    {
        "brand_domain": "cetaphil.in",
        "brand_name": "Cetaphil India",
        "brand_url": "https://www.cetaphil.in",
        "platform": "custom",
        "css_selector": ".ingredients-copy p",
        "requires_js": True,
        "js_action": "scroll to load product detail sections",
        "notes": "Cetaphil India runs on a custom (Sitecore-based) platform. The full INCI is "
                 "inside .ingredients-copy p, visible after scrolling. Confirmed via DevTools.",
        "sample_url": "https://www.cetaphil.in/products/cleansers/gentle-skin-cleanser/8906005274105.html",
        "sample_inci_preview": "Aqua, Glycerin, Cetearyl Alcohol, Panthenol, Niacinamide",
        "confidence": 0.95,
        "status": "active",
    },
    {
        "brand_domain": "hibiscusmonkey.com",
        "brand_name": "Hibiscus Monkey",
        "brand_url": "https://hibiscusmonkey.com",
        "platform": "woocommerce",
        "css_selector": "#tab2 .product_extra p",
        "requires_js": True,
        "js_action": "click [class*=\"tab\"]:has-text(\"INGREDIENT\") to reveal ingredients tab",
        "notes": "Product page has tabbed layout; ingredients are in #tab2 (second tab). "
                 "Playwright tab click reveals the tab content. Generic tab click selector "
                 "in _INGREDIENT_CLICK_SELECTORS handles this automatically.",
        "sample_url": "https://hibiscusmonkey.com/product/coconut-milk-body-butter/",
        "sample_inci_preview": "Cocos Nucifera (Coconut Milk Oil), Bergamot Oil, Geranium Oil, Patchouli Oil",
        "confidence": 0.90,
        "status": "active",
    },
    {
        "brand_domain": "thefaceshop.in",
        "brand_name": "The Face Shop India",
        "brand_url": "https://www.thefaceshop.in",
        "platform": "shopify",
        "css_selector": "details[open=\"\"] span.metafield-multi_line_text_field",
        "requires_js": True,
        "js_action": "click summary:has-text(\"INGREDIENT\") to expand accordion",
        "notes": "Multiple accordion sections on page; Playwright clicks the INGREDIENTS "
                 "summary, setting open=\"\" on that <details> element. Scoping to "
                 "details[open=\"\"] ensures we select only the clicked accordion's "
                 "metafield span rather than description spans in other accordions.",
        "sample_url": "https://www.thefaceshop.in/products/rice-water-bright-cleansing-foam",
        "sample_inci_preview": "water/eau, myristic acid, glycerin, potassium hydroxide, stearic acid",
        "confidence": 0.92,
        "status": "active",
    },
    {
        "brand_domain": "neutrogena.in",
        "brand_name": "Neutrogena India",
        "brand_url": "https://www.neutrogena.in",
        "platform": "nextjs",
        "css_selector": "[data-sb-field-path=\".content\"] .rich-text p",
        "requires_js": True,
        "js_action": "click [class*=\"accordion\"]:has-text(\"Ingredients\") to expand accordion",
        "notes": "CDN blocks headless browsers — requires ScraperAPI proxy (listed in "
                 "_CDN_BLOCKED_DOMAINS). Multiple .rich-text sections on page (description, "
                 "key benefits, how-to-use, INCI). Scoping to [data-sb-field-path=\".content\"] "
                 "targets only the Storyblok CMS content block inside the Ingredients accordion.",
        "sample_url": "https://www.neutrogena.in/face/ultra-gentle-cleanser",
        "sample_inci_preview": "Water, Glycerin, Cocamidopropyl Betaine, Lauryl Glucoside, Sodium Cocoyl Isethionate",
        "confidence": 0.92,
        "status": "active",
    },
    {
        "brand_domain": "aqualogica.in",
        "brand_name": "Aqualogica",
        "brand_url": "https://aqualogica.in",
        "platform": "shopify",
        "css_selector": "details[class*=\"ingredient\"] .hdt-product-accordion__content p",
        "requires_js": True,
        "js_action": "scroll to 3000px and 6000px to trigger IntersectionObserver lazy loading",
        "notes": "Product accordion sections are lazy-loaded via IntersectionObserver — "
                 "they only appear in DOM after scrolling. Ingredient accordion class varies "
                 "by product: 'ingredients-list' (face wash/sunscreen) vs 'ingredient-list' "
                 "(moisturizer). Using [class*=\"ingredient\"] handles both.",
        "sample_url": "https://aqualogica.in/products/detan-smoothie-face-wash-100ml-1",
        "sample_inci_preview": "Aqua, Sodium Lauroyl Sarcosinate, Polyacrylate-33, Cocamidopropyl Betaine",
        "confidence": 0.90,
        "status": "active",
    },
    {
        "brand_domain": "barenecessities.in",
        "brand_name": "Bare Necessities",
        "brand_url": "https://barenecessities.in",
        "platform": "shopify",
        "css_selector": ".grouped-content-content span",
        "requires_js": True,
        "js_action": "Playwright scroll to load tabbed product content",
        "notes": "INCI is inside a tabbed accordion (li.grouped-content-content). "
                 "Multiple tabs exist (description, ingredients, how-to-use); "
                 "_looks_like_inci filtering picks the right one. Needs Playwright.",
        "sample_url": "https://barenecessities.in/products/rainforest-deep-hydration-vegan-moisturizer-natural-dry-skin",
        "sample_inci_preview": "Ingredients: Aqua, Cetearyl Olivate, Sorbitan Olivate, Caprylic/Capric Triglyceride",
        "confidence": 0.90,
        "status": "active",
    },
    {
        "brand_domain": "foxtale.in",
        "brand_name": "Foxtale",
        "brand_url": "https://foxtale.in",
        "platform": "shopify",
        "css_selector": "div.text-12! > p",
        "requires_js": True,
        "js_action": "Playwright scroll to load product sections",
        "notes": "Full Ingredient List section uses Tailwind class 'text-12!' (with ! modifier). "
                 "Lazy-loaded, needs Playwright with scroll. The > chain navigation in "
                 "validate_selector finds the div by its class (! supported in regex).",
        "sample_url": "https://foxtale.in/products/retinol-anti-ageing-night-serum",
        "sample_inci_preview": "Aqua, Propylene glycol, Dicaprylyl Carbonate, Dimethicone",
        "confidence": 0.92,
        "status": "active",
    },
    {
        "brand_domain": "thedermaco.com",
        "brand_name": "The Derma Co",
        "brand_url": "https://thedermaco.com",
        "platform": "shopify",
        "css_selector": "details.ingredients-list > div.product-detail-card-description",
        "requires_js": False,
        "js_action": None,
        "notes": "Full INCI in static HTML: details.ingredients-list contains "
                 "div.product-detail-card-description with the ingredient text. "
                 "The <details> element is collapsed by default but text is in DOM.",
        "sample_url": "https://thedermaco.com/products/1-salicylic-acid-serum",
        "sample_inci_preview": None,
        "confidence": 0.95,
        "status": "active",
    },
    # ── Newly fixed needs_review brands ──────────────────────────────────────
    {
        "brand_domain": "letshyphen.com",
        "brand_name": "Let's Hyphen",
        "brand_url": "https://letshyphen.com",
        "platform": "shopify",
        "css_selector": ".accordion__content p",
        "requires_js": True,
        "js_action": "Playwright scroll to load accordion sections",
        "notes": "Full INCI inside .accordion__content p — ingredient accordion is "
                 "present in DOM after Playwright scroll. Confirmed returns "
                 "'INGREDIENTS: Purified Water, Propanediol, 3-O-Ethyl Ascorbic Acid...'.",
        "sample_url": "https://letshyphen.com/products/vitamin-c-serum",
        "sample_inci_preview": "INGREDIENTS: Purified Water, Propanediol, 3-O-Ethyl Ascorbic Acid",
        "confidence": 0.90,
        "status": "active",
    },
    {
        "brand_domain": "brillare.net",
        "brand_name": "Brillare",
        "brand_url": "https://brillare.net",
        "platform": "shopify",
        "css_selector": 'details[open=""] .metafield-rich_text_field p',
        "requires_js": True,
        "js_action": 'click summary:has-text("Full Ingredient") to expand Full Ingredients accordion',
        "notes": "Multiple details.custom_f2 elements share the same class (description, "
                 "FAQ, Full Ingredients, etc.). Clicking summary:has-text('Full Ingredient') "
                 "sets open=\"\" on ONLY that <details> element — scoping to details[open=\"\"] "
                 "avoids picking up description text from other accordions that also pass "
                 "_looks_like_inci (≥5 commas). summary:has-text('Full Ingredient') placed "
                 "before generic 'Ingredient' in _INGREDIENT_CLICK_SELECTORS to avoid nav clicks.",
        "sample_url": "https://brillare.net/products/lemon-vitamin-c-brightening-face-wash",
        "sample_inci_preview": "CITRUS MEDICA LIMONUM (LEMON) PEEL WATER, MELALEUCA ALTERNAFOLIA",
        "confidence": 0.92,
        "status": "active",
    },
    {
        "brand_domain": "kiehls.in",
        "brand_name": "Kiehl's India",
        "brand_url": "https://www.kiehls.in",
        "platform": "custom",
        "css_selector": "div.ingredient",
        "requires_js": True,
        "js_action": "Playwright scroll to trigger lazy-loaded ingredient popup content",
        "notes": "INCI lives in div.ingredient (the popup content panel). "
                 "Each ingredient is in its own <p> tag with 0 commas — "
                 "_looks_like_inci extended to accept inci_terms >= 5 for this pattern. "
                 "selector_to_regex uses \\b word boundaries to prevent div.ingredient "
                 "matching div.ingredients-popup (same class prefix).",
        "sample_url": "https://www.kiehls.in/ultra-facial-cream",
        "sample_inci_preview": "AQUA / WATER GLYCERIN AMMONIUM LAURYL SULFATE PROPYLENE GLYCOL",
        "confidence": 0.88,
        "status": "active",
    },
    # ── Confirmed no_inci brands (no machine-readable INCI in HTML) ───────────
    {
        "brand_domain": "thebodyshop.in",
        "brand_name": "The Body Shop India",
        "brand_url": "https://www.thebodyshop.in",
        "platform": "nextjs",
        "css_selector": "tbsdata:",
        "requires_js": False,
        "js_action": None,
        "notes": "Next.js + Redux site. Full INCI in __NEXT_DATA__ JSON under "
                 "props.pageProps.initialState.productDetailReducer.product.customAttributes — "
                 "find item with attribute_code == 'ingredients', decode \\u003cp\\u003e-encoded "
                 "HTML value. No JS click needed; plain httpx fetch is sufficient.",
        "sample_url": "https://www.thebodyshop.in/tea-tree-facial-wash-250ml/p/p167004",
        "sample_inci_preview": "Aqua/Water/Eau, Sodium Laureth Sulfate, Glycerin, Cocamidopropyl Betaine",
        "confidence": 0.92,
        "status": "active",
    },
    {
        "brand_domain": "paulaschoice.in",
        "brand_name": "Paula's Choice India",
        "brand_url": "https://www.paulaschoice.in",
        "platform": "shopify",
        "css_selector": "paulaschoice:",
        "requires_js": False,
        "js_action": None,
        "notes": "Full INCI in span.metafield-multi_line_text_field inside the jsc-readMore div "
                 "containing <h2>INGREDIENTS</h2>. Span has two sections: 'Key Ingredients' and "
                 "'All Ingredients' — split on 'All Ingredients' to get just the INCI. "
                 "Strip \\u2060 (WORD JOINER) zero-width chars injected after each ingredient name. "
                 "Static HTML, no JS needed.",
        "sample_url": "https://www.paulaschoice.in/products/clear-pore-normalizing-cleanser",
        "sample_inci_preview": "Salicylic Acid, Water, Sodium Lauroyl Sarcosinate, Acrylates/Steareth-20 Methacrylate Copolymer",
        "confidence": 0.92,
        "status": "active",
    },
    # ── Additional alternate-domain entries ──────────────────────────────────
    {
        "brand_domain": "brillare.co.in",
        "brand_name": "Brillare (co.in)",
        "brand_url": "https://www.brillare.co.in",
        "platform": "shopify",
        "css_selector": 'details[open=""] .metafield-rich_text_field p',
        "requires_js": True,
        "js_action": 'click summary:has-text("Full Ingredient") to expand Full Ingredients accordion',
        "notes": "Same Shopify theme template as brillare.net — identical DOM structure and selector. "
                 "Multiple details.custom_f2 elements; clicking 'Full Ingredients' summary sets "
                 "open=\"\" only on that accordion, scoping the selector uniquely.",
        "sample_url": "https://www.brillare.co.in/products/mini-oil-away-serum-mist-10-ml",
        "sample_inci_preview": "CITRUS MEDICA LIMONUM (LEMON) PEEL WATER, MELALEUCA ALTERNAFOLIA",
        "confidence": 0.92,
        "status": "active",
    },
    {
        "brand_domain": "beyondbeyond.co.in",
        "brand_name": "Beyond Beyond",
        "brand_url": "https://beyondbeyond.co.in",
        "platform": "shopify",
        "css_selector": "itemlist:div.ingredientLists##div.item_d",
        "requires_js": False,
        "js_action": None,
        "notes": "Ingredients Overview section has individual ingredient tiles (div.item_d) inside "
                 "div.ingredientLists. Each tile's ingredient name is a raw text node before a "
                 "child <span.ingreInfo> tooltip — itemlist: extractor takes text before the first "
                 "child tag, strips whitespace, and joins all tiles with ', '. Static HTML, no JS.",
        "sample_url": "https://beyondbeyond.co.in/products/deep-clean-enzyme-cleanser",
        "sample_inci_preview": "Talc, Maltodextrin, Sodium Lauroyl Glutamate, Hydroxyethylcellulose",
        "confidence": 0.88,
        "status": "active",
    },
    {
        "brand_domain": "kamaayurveda.in",
        "brand_name": "Kama Ayurveda (India)",
        "brand_url": "https://www.kamaayurveda.in",
        "platform": "nextjs",
        "css_selector": None,
        "requires_js": False,
        "js_action": None,
        "notes": "Next.js PWA with CSS Module hashed class names. The 'Ingredients' section "
                 "shows Ayurvedic/botanical ingredient image tiles (not INCI format). The full "
                 "INCI list exists only as a printed label photo in the product image gallery "
                 "(filename pattern: *-ingredients-*.jpg) — no machine-readable INCI text "
                 "in HTML or GraphQL API responses.",
        "sample_url": None,
        "sample_inci_preview": None,
        "confidence": 0.97,
        "status": "no_inci",
    },
    {
        "brand_domain": "aveeno.in",
        "brand_name": "Aveeno India",
        "brand_url": "https://www.aveeno.in",
        "platform": "nextjs",
        "css_selector": "rsc:drawer.body",
        "requires_js": False,
        "js_action": None,
        "notes": "CDN blocks headless browsers — requires ScraperAPI proxy (listed in "
                 "_CDN_BLOCKED_DOMAINS). INCI lives in a Storyblok drawer component that "
                 "only mounts into the DOM when the 'FULL LIST OF INGREDIENTS' button is "
                 "clicked (Radix UI Sheet). Playwright click does not trigger React's "
                 "synthetic event system through the proxy. Instead, the ingredient text "
                 "is extracted from the Next.js RSC JSON payload in the initial HTML: "
                 "data-sb-field-path=\".drawer.body\" + dangerouslySetInnerHTML.__html "
                 "contains the full INCI as \\u003cp\\u003e-encoded HTML. "
                 "Uses rsc:drawer.body selector + _extract_from_rsc() + _fetch_page_with_proxy().",
        "sample_url": "https://www.aveeno.in/products/baby/baby-cleansing-therapy-moisturising-wash",
        "sample_inci_preview": "Water, Sodium Trideceth Sulfate, Sodium Lauroamphoacetate. Caprylic/Capric Triglyceride, Glycerin",
        "confidence": 0.90,
        "status": "active",
    },
    # ── Pattern 2 fixes: brands where auto-detection failed to find a product URL ──
    {
        "brand_domain": "ceraveindia.com",
        "brand_name": "CeraVe India",
        "brand_url": "https://ceraveindia.com",
        "platform": "custom",
        "css_selector": 'accordion[event-action="ingredients"] p',
        "requires_js": False,
        "js_action": None,
        "notes": "Product URLs follow /ceramides-skin-care/{category}/{product-slug} — NOT "
                 "/products/. INCI is inside a <accordion> Web Component with "
                 "event-action=\"ingredients\" attribute. Content is in static HTML "
                 "(display:none initially but always in DOM). Plain httpx fetch works.",
        "sample_url": "https://ceraveindia.com/ceramides-skin-care/moisturisers/moisturising-cream",
        "sample_inci_preview": "Aqua / Water / Eau, Glycerin, Cetearyl Alcohol, Caprylic/Capric Triglyceride",
        "confidence": 0.93,
        "status": "active",
    },
    {
        "brand_domain": "garnier.in",
        "brand_name": "Garnier India",
        "brand_url": "https://www.garnier.in",
        "platform": "custom",
        "css_selector": "#ingredients-list p",
        "requires_js": False,
        "js_action": None,
        "notes": "Sitecore CMS. Product URLs follow /about-our-brands/{range}/{product-slug}. "
                 "INCI in <div id=\"ingredients-list\" data-ioplist=\"\"> > <p>. "
                 "Server-rendered, no JS needed. [data-ioplist] p is an equivalent selector.",
        "sample_url": "https://www.garnier.in/about-our-brands/skin-naturals/bright-complete/vitamin-c-face-serum",
        "sample_inci_preview": "AQUA / WATER, GLYCERIN, ALCOHOL, DIPROPYLENE GLYCOL, BUTYLENE GLYCOL",
        "confidence": 0.95,
        "status": "active",
    },
    {
        "brand_domain": "olayskincare.com",
        "brand_name": "Olay India",
        "brand_url": "https://olayskincare.com/en-in/",
        "platform": "nextjs",
        "css_selector": "nextdata:",
        "requires_js": False,
        "js_action": None,
        "notes": "Next.js site. Product URLs at /en-in/skin-care-products/{product-slug}/. "
                 "INCI embedded in __NEXT_DATA__ JSON under "
                 "productCollection.items[0].activeIngredients.contentsCollection.items[0]"
                 ".descriptionListingCollection.items[0].body. "
                 "Uses nextdata: selector + _extract_from_next_data() which recursively "
                 "searches 'body' keys and returns the first that passes _looks_like_inci.",
        "sample_url": "https://olayskincare.com/en-in/skin-care-products/retinol24-night-serum-with-retinol-and-vitamin-b3/",
        "sample_inci_preview": "Aqua, Dimethicone, Glycerin, Retinyl Propionate, Caprylic/Capric Triglyceride",
        "confidence": 0.90,
        "status": "active",
    },
    # ── Brands where extraction is structurally infeasible via CSS selectors ──
    {
        "brand_domain": "mamaearth.in",
        "brand_name": "Mamaearth",
        "brand_url": "https://mamaearth.in",
        "platform": "nextjs",
        "css_selector": "mamaearthtable:",
        "requires_js": False,
        "js_action": None,
        "notes": "Mamaearth Next.js site stores INCI in __NEXT_DATA__ JSON under "
                 "props.pageProps.cmsContent — find entry with 'Ingredient List' in its title list, "
                 "extract content field (HTML table: Ingredient | Type | Source | How It Helps). "
                 "mamaearthtable: extractor parses the table and joins first-column values with ', '.",
        "sample_url": "https://mamaearth.in/product/tea-tree-face-wash",
        "sample_inci_preview": "Tea Tree Water, Sodium Lauroyl Sarcosinate, Acrylates Copolymer, Cocamidopropyl Betaine",
        "confidence": 0.90,
        "status": "active",
    },
    {
        "brand_domain": "faebeauty.in",
        "brand_name": "FAE Beauty",
        "brand_url": "https://www.faebeauty.in",
        "platform": "shopify",
        "css_selector": "faelink:https://www.faebeauty.in/pages/ingredients-1",
        "requires_js": False,
        "js_action": None,
        "notes": "All FAE Beauty product ingredients are listed on one shared page "
                 "(/pages/ingredients-1). Each product is identified by a <a href> whose "
                 "URL contains the product slug. The INCI text follows the anchor tag's "
                 "parent bold/italic wrapper until the next product anchor. "
                 "faelink: extractor fetches the shared page, matches by slug, and extracts INCI. "
                 "Not all products may be listed (~21 found on that page as of 2026-04).",
        "sample_url": "https://www.faebeauty.in/collections/lip-whip/products/lip-whip-liquid-matte-lipstick-new-landing",
        "sample_inci_preview": "Isododecane, Cyclopentasiloxane, Dimethicone Crosspolymer, Dimethicone",
        "confidence": 0.85,
        "status": "active",
    },
    {
        "brand_domain": "discoverpilgrim.com",
        "brand_name": "Discoverpilgrim",
        "brand_url": "https://www.discoverpilgrim.com",
        "platform": "shopify",
        "css_selector": "tablecol:.ingredients-table-container",
        "requires_js": False,
        "js_action": None,
        "notes": "Pilgrim exposes an ingredient breakdown table (Ingredient / Type / Source / Benefit). "
                 "The full table is present in static HTML — no JS needed. "
                 "tablecol: extractor finds .ingredients-table-container, iterates all <tbody> rows, "
                 "extracts the first <td> (ingredient name) per row, and joins with ', '.",
        "sample_url": "https://www.discoverpilgrim.com/products/vitamin-c-brightening-gel-face-wash-pack-of-2",
        "sample_inci_preview": "Aqua, Cocamidopropyl Betaine, Coco-Glucoside, Sodium Cocoyl Isethionate",
        "confidence": 0.88,
        "status": "active",
    },
    {
        "brand_domain": "ponds.in",
        "brand_name": "Ponds India",
        "brand_url": "https://www.ponds.in",
        "platform": "custom",
        "css_selector": None,
        "requires_js": False,
        "js_action": None,
        "notes": "Ponds India INCI is only available as a product label image — "
                 "no machine-readable ingredient text in the HTML.",
        "sample_url": None,
        "sample_inci_preview": None,
        "confidence": 1.0,
        "status": "no_inci",
    },
    {
        "brand_domain": "himalayawellness.in",
        "brand_name": "Himalaya",
        "brand_url": "https://www.himalayawellness.in",
        "platform": "custom",
        "css_selector": None,
        "requires_js": False,
        "js_action": None,
        "notes": "Himalaya products do not expose standard INCI lists — "
                 "ingredients are described in Ayurvedic/botanical format, not INCI notation.",
        "sample_url": None,
        "sample_inci_preview": None,
        "confidence": 1.0,
        "status": "no_inci",
    },
]


async def _get_conn() -> psycopg.AsyncConnection:
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row)


async def main() -> None:
    conn = await _get_conn()
    try:
        async with conn.cursor() as cur:
            for schema in KNOWN_SCHEMAS:
                await cur.execute("""
                    INSERT INTO scraping.ingredient_strategies
                      (brand_domain, brand_name, brand_url, platform,
                       css_selector, requires_js, js_action, notes,
                       sample_url, sample_inci_preview, confidence,
                       detection_model, detected_at, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s)
                    ON CONFLICT (brand_domain) DO UPDATE SET
                      css_selector        = EXCLUDED.css_selector,
                      requires_js         = EXCLUDED.requires_js,
                      js_action           = EXCLUDED.js_action,
                      notes               = EXCLUDED.notes,
                      sample_url          = EXCLUDED.sample_url,
                      confidence          = EXCLUDED.confidence,
                      detection_model     = EXCLUDED.detection_model,
                      detected_at         = now(),
                      status              = EXCLUDED.status
                """, (
                    schema["brand_domain"], schema["brand_name"], schema["brand_url"],
                    schema["platform"], schema["css_selector"], schema["requires_js"],
                    schema["js_action"], schema["notes"], schema["sample_url"],
                    schema["sample_inci_preview"], schema["confidence"],
                    "manual", schema["status"],
                ))
                log.info("schema_seeded",
                         brand=schema["brand_name"],
                         domain=schema["brand_domain"],
                         selector=schema["css_selector"],
                         status=schema["status"])
        await conn.commit()
        log.info("seed_complete", count=len(KNOWN_SCHEMAS))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
