# v0 → v1 Schema Changelog

Each delta cites scorecard evidence from the 60-sample face skincare spike (2026-04-24).

## Delta 1: Tira __NEXT_DATA__ — scraper_configs.extraction_method
**Evidence:** Tira scored 0% on ALL fields (brand_name, canonical_name, current_price, stock_status, images, variants — all absent). Root cause: Tira is a React/Next.js app; the HTML parser receives pre-hydration markup. All product data is embedded in a `<script id="__NEXT_DATA__">` JSON blob that our current parser ignores.
**Delta:** Add `extraction_method TEXT NOT NULL DEFAULT 'json_ld'` to `scraping.scraper_configs`. Valid values: `json_ld`, `next_data`, `css_selector`, `regex`, `llm`. Tira configs default to `next_data`.

## Delta 2: Ingredients — ingredient_extraction_queue
**Evidence:** Ingredients scored 0% across ALL 7 retailers (60/60 samples missing). Shopify /products.json structurally never exposes ingredients. Marketplace JSON-LD rarely includes them. This is not a parser bug — ingredients require a dedicated product-page scrape with retailer-specific selectors or vision LLM (Tier 3/4).
**Delta:** Add `scraping.ingredient_extraction_queue` table. Products enter this queue after initial catalog scrape; a separate worker visits the product page and extracts the ingredient text. Add `ingredient_scrape_status TEXT NOT NULL DEFAULT 'pending'` to `core.products`.

## Delta 3: Offers — separate promotions table
**Evidence:** Offers scored 0% across ALL 7 retailers. Promotional banners are JS-rendered, session-specific, and site-specific. They cannot be extracted via JSON-LD and change hourly.
**Delta:** Remove `current_offers JSONB` from `core.retailer_listings`. Add `core.promotions` table (ephemeral, listing-scoped, time-bounded). This keeps the listings table clean.

## Delta 4: Rating — split into value + count columns
**Evidence:** Purplle provided rating in 90% of samples (JSON-LD aggregateRating). Current model stores as raw string "4.3 (212)" which loses queryability. Other retailers: 0% — ratings not in Shopify /products.json or Tira JSON-LD.
**Delta:** Replace `rating_raw TEXT` in `core.retailer_listings` with `rating_value NUMERIC(3,2)` and `rating_count INTEGER`, both nullable. Keep a `rating_raw TEXT` as the verbatim source string for audit.

## Delta 5: description_source tracking
**Evidence:** Description presence ranges from 0% (Purplle, Tira) to 100% (The Derma Co) across Shopify brands. Shopify body_html is often empty because brand sites use custom page builders. When body_html is empty, the description must come from a product-page scrape.
**Delta:** Add `description_source TEXT` to `core.products`. Values: `shopify_body_html`, `product_page_scrape`, `llm_extracted`, `manual`. Helps track data quality and guides re-scrape logic.

## Delta 6: compare_at_price confirmed nullable
**Evidence:** Absent for Purplle (0/10), Tira (0/10), The Derma Co (0/8). Present and reliable for the other 4 Shopify brands (100%). Not universal.
**Delta:** No structural change — v0 already has `compare_at_price NUMERIC(10,2)` as nullable. Confirmed correct. Document as intentional.

## Delta 7: category_hint → taxonomy layer confirmed
**Evidence:** category_hint 0% on Purplle and Tira (marketplaces). Partially reliable on Shopify (38–100%, product_type field unreliable). Consistent with brainstorm finding ("Launching", blank strings).
**Delta:** No structural change to v0 taxonomy table design. Confirms `taxonomy.categories` + `taxonomy.mappings` tables are necessary. Adds confidence to the decision.

## Delta 8: brand_name sourcing — product level, not listing level
**Evidence:** brand_name 100% reliable on all 5 Shopify brands (from /products.json `vendor` field). 0% on Tira (absent in JSON-LD — Tira doesn't include brand in their JSON-LD schema).
**Delta:** Clarify that `brand_id` on `core.products` is the authoritative source. `brand_name` from scraping is a discovery hint used during dedup, not a stored field on listings. No structural change needed.
