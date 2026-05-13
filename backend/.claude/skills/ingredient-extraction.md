---
name: wand-ingredient-extraction
description: Brand-specific INCI extraction patterns, known gaps, and debugging learnings for the Wand skincare aggregator scraper. Use whenever working on ingredient extraction for this project.
---

# Wand Ingredient Extraction — Learnings & Patterns

## Architecture

- **File**: `backend/scraper/fetchers/ingredient_extractor.py`
- **Queue table**: `scraping.ingredient_extraction_queue` — statuses: `pending`, `done`, `failed`, `no_inci_html`
- **Strategy table**: `scraping.ingredient_strategies` — per-brand `css_selector`, `requires_js`, `status`
- **Custom prefix dispatch**: `_extract_with_strategy()` routes on `css_selector` prefix (e.g. `mamaearthtable:`, `tbsdata:`, `bojmodal:`)
- **Validation**: `_looks_like_inci()` in `scraper/ingredient_schema_detector.py`
- **Playwright**: `_fetch_playwright()` — scrolls to 3000px + 6000px, tries `_INGREDIENT_CLICK_SELECTORS`

## Implemented Custom Extractors (prefix → function)

| Prefix | Brand | Notes |
|---|---|---|
| `mamaearthtable:` | Mamaearth | Reads `cmsContent` from `__NEXT_DATA__`; falls back to `_next/data/{buildId}/product/{variant_slug}.json` API when `showMetaPDP: True` returns empty cmsContent |
| `tbsdata:` | The Body Shop India | Reads `customAttributes.ingredients` from Next.js `__NEXT_DATA__` |
| `bojmodal:` | Beauty of Joseon | Playwright renders `product-modal__outer` dialog; replaces `<br>` with `, ` before stripping HTML; strips ACTIVE/INACTIVE INGREDIENT headers |
| `pixiin:` | Pixi Beauty India | Falls back to `ingredients-popup__inner div.font-roboto` for bundle products |
| `reequil:` | Re'equil | Selector is `.accordion-details .accordion-details__content p` (NOT `details.accordion-details` — pack-of-2 uses `<div>` not `<details>`) |
| `letshyphen:` | Let's Hyphen | Extracts `##Ingredients: @@<INCI>##` from Shopify JS blob |
| `dabtofab:` | Dab to Fab | INCI in `<p>` inside `.accordion-content` after `<h3>Full Ingredients</h3>` |
| `hibiscusmonkey:` | Hibiscus Monkey | Each ingredient in `<div class="pop-ingrd-accrdion-heading"><strong>Name</strong></div>`; collects all and joins with `, ` |
| `drsheths:` | Dr. Sheth's | — |
| `dearth:` | Daughter Earth | Shogun page builder — async fetch, not renderable |
| `kiehls:` | Kiehl's India | `ingredients-popup-inner` div; only ~3/43 products have this modal |
| `deconstruct:` | The Deconstruct | — |
| `earthrhythm:` | Earth Rhythm | — |
| `clayco:` | Clay Co | — |
| `juicychemistry:` | Juicy Chemistry | — |
| `brillare:` | Brillare | Static extraction |
| `paulaschoice:` | Paula's Choice India | — |
| `deyga:` | Deyga | — |
| `dearist:` | The Dearist | — |
| `quenchbotanics:` | Quench Botanics | — |
| `barenecessities:` | Bare Necessities | — |
| `biestyle:` | Beauty by Boe | — |
| `raisebeauty:` | Raise Beauty | — |
| `inciparagraph:` | Various | Generic paragraph extractor |
| `embryolisse:` | Embryolisse | — |
| `nextdata:` | Various | Generic `__NEXT_DATA__` extractor |
| `tablecol:` | Various | Table column extractor |
| `rsc:` | Various | React Server Components |
| `faelink:` | FAE Beauty | — |
| `itemlist:` | Various | List item extractor |

## Key Brand-Specific Findings

### Mamaearth
- **`showMetaPDP: True`** products return `cmsContent: []` in static HTML
- **Fix**: Read `configurable_options[optionId][i].url_key` from `__NEXT_DATA__`, then fetch `/_next/data/{buildId}/product/{variant_slug}.json` — this always has full `cmsContent` including the ingredient table
- Done products have `cmsContent` with "Ingredients List" entry containing an HTML `<table>` with 4 columns: Ingredient | Type | Where Is It From | How It Helps
- Extract first-column `<td>` values, join with `, `

### The Body Shop India
- 109 remaining `no_inci_html` = genuinely no INCI in Magento backend (not a scraping failure)
- Products where INCI is visible in the UI have it in `customAttributes.ingredients` in `__NEXT_DATA__`

### Beauty of Joseon
- `bojmodal:` requires Playwright (JS renders the modal)
- Sunscreen products (US-format OTC) have `<br>`-separated ingredients with ACTIVE/INACTIVE INGREDIENT headers — strip headers, replace `<br>` with `, `
- Mini/sample/free-gift products rarely have the modal

### Kiehl's India
- Most products are JS-heavy with no static INCI
- Only ~3/43 have the `ingredients-popup-inner` div
- Remaining 42 are legitimately not extractable without an API call

### Plum Goodness
- 2025 template: INCI fully dynamic, not in static HTML or Playwright render
- Old template (pre-2025): `div.ingredient-hidden span.metafield-multi_line_text_field`

### Ponds India
- Confirmed: INCI **not published anywhere** on ponds.in website
- Strategy should be `status='no_inci'`, not failed

### Innisfree India
- Most products don't have INCI published on the Indian site
- Some have `div.metafield-rich_text_field` accordion (done products)

### Fixderma / BRWN / Bioderma / mCaffeine / Let's Hyphen
- INCI only available as **images of product packaging**
- Requires Claude vision API (Haiku model) to extract
- See vision INCI spike results for feasibility

## CDN-Blocked Domains
Only `neutrogena.in` and `aveeno.in` need ScraperAPI proxy.
ScraperAPI key: `SCRAPERAPI_KEY` in `.env`. Plan: 5,000 req/mo ($49). Resets monthly.

## Catalog Filtering (UI)
Products excluded from catalog UI (added to `search_products()` WHERE clause):
- combos, duos, trios, kits, sets (trailing), packs, bundles, hampers
- gift items, free samples (`-free` ending, `free -` prefix, `🎁`)
- swatches, test/internal products
- accessories: brushes, tote bags, hoodies, scrunchies, gua sha, soap savers, pillowcases

## Genuinely No-INCI Brands (do not retry)
These brands don't publish INCI anywhere:
- **Himalaya Wellness** (~405 products)
- **Lotus Herbals** (~355 products)
- **Kama Ayurveda** (~124 products)
- **Ponds India** (~45 products)
- **Innisfree India** (most of ~42 products)
- **Forest Essentials** (~43 products)

## Common Debugging Patterns

```python
# Check no_inci_html count by brand
SELECT r.slug, r.name, count(*) 
FROM scraping.ingredient_extraction_queue q
JOIN core.retailers r ON r.id = rl.retailer_id
JOIN core.retailer_listings rl ON rl.id = q.listing_id
WHERE q.status = 'no_inci_html'
GROUP BY r.slug, r.name ORDER BY count(*) DESC;

# Reset specific items to pending
UPDATE scraping.ingredient_extraction_queue 
SET status='pending', attempts=0 
WHERE id = ANY(ARRAY[...]);

# Check a brand's strategy
SELECT * FROM scraping.ingredient_strategies 
WHERE brand_url ILIKE '%brandname%' OR brand_name ILIKE '%brandname%';
```

## Running Extraction
```bash
# Run for specific brand
.venv/bin/python -m scraper.run_ingredients --retailers brandslug

# Dry run
.venv/bin/python -m scraper.run_ingredients --dry-run --limit 5

# Check results
.venv/bin/python -c "
from pathlib import Path; from dotenv import load_dotenv; load_dotenv(Path('.env'))
import psycopg; from app.config import settings
dsn = settings.database_url.replace('postgresql+psycopg://', 'postgresql://')
conn = psycopg.connect(dsn, row_factory=psycopg.rows.dict_row)
# ... your query
"
```
