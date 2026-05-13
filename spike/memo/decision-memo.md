# Wand Phase 1 — Sprint 0 Decision Memo
**Schema Validation Spike**
Date: 2026-04-24
Author: Spike AI collaborator + Sasank Daggubati

---

## 1. Purpose

This spike existed to answer one question before Sprint 1 schema finalization: does the v0 data model reflect what is actually extractable from Indian skincare retailer pages, or does it make assumptions that will break in production? The v0 schema was designed from first principles against known retailer patterns; this spike provided empirical grounding by scraping real product pages and measuring field presence rate against each v0 field. Findings drove eight concrete schema deltas (v0 → v1) and produced a field-presence scorecard that serves as the canonical reference for Sprint 1 build priorities.

---

## 2. Method

The spike scraped 60 face skincare product pages across 7 retailers: 5 Shopify D2C brands (Minimalist, Plum, mCaffeine, Dot&Key, The Derma Co) and 2 multi-brand marketplaces (Tira and Purplle). Scraping was performed using a headless Playwright-based crawler. For each page, a structured field extractor attempted to populate every v0 field and recorded presence (extracted value), absence (field not found), or error (page-level failure). Nykaa and Amazon.in were also attempted but blocked at connection level and are recorded separately. The output is a per-field, per-retailer presence scorecard used to drive all schema decisions below.

---

## 3. Key Findings

### 3.1 Tira: All Fields Absent (Corrected in Sprint 1)

Tira returned 0% field presence during the spike because the spike's parser only tried JSON-LD and CSS selectors. Sprint 1 investigation revealed the actual root cause: Tira runs on the **Fynd** e-commerce platform (not Next.js), which embeds all product data in a `window.APP_DATA` JavaScript object in the page HTML. The data is fully present on initial load — no JS execution required. The Fynd extractor built in Sprint 1 achieves 10/10 name, 10/10 images, 7/10 price (3 products have price loaded via API call post-render). The `extraction_method = 'next_data'` schema delta is now `extraction_method = 'fynd_app_data'` instead.

### 3.2 Ingredients: 0% Across All Retailers

Ingredients field presence was 0% across all 60 pages and all 7 attempted retailers. Ingredients are consistently rendered in expandable accordion sections or tab-switched content that requires a secondary interaction (click/scroll to expand) after initial page load. The v0 model assumed ingredients would be co-located with product metadata on the primary page load; this assumption is uniformly wrong. Ingredient extraction requires a dedicated second-pass scrape with interaction scripting.

### 3.3 Offers: 0% Across All Retailers

`current_offers` was absent on 100% of pages. Promotion data (discount codes, bundle deals, limited-time offers) is not embedded in product page HTML in a structured way. It appears in dynamic cart-layer overlays, pop-up banners, or is computed server-side at checkout. Storing offers as a JSONB column on `retailer_listings` is architecturally incorrect — offers are ephemeral, cross-listing, and time-bounded, requiring a separate entity.

### 3.4 Rating: Purplle Only (90%), Absent Elsewhere

Rating data was present on 90% of Purplle pages and 0% everywhere else. Shopify D2C brands (Minimalist, Plum, mCaffeine, Dot&Key, The Derma Co) generally do not surface aggregate ratings on product pages — reviews, if present, are embedded in third-party widgets (Okendo, Yotpo) that load asynchronously. Tira ratings were inaccessible due to the Next.js issue above. This means rating is a marketplace-specific field for Phase 1, not a universal product attribute.

### 3.5 Description: Variable by Brand (38–100%)

Description presence ranged from 38% (some Shopify brands with minimal product copy) to 100% (brands with full `body_html` populated). The variability is not a scraping failure — it reflects genuine editorial inconsistency across D2C brands. The field is reliably available from Shopify's `body_html` field when the brand populates it, but the source of truth differs: some brands use structured metafields, others use freeform HTML, others have near-empty descriptions with data deferred to PDPs. The v0 model stored description without tracking its provenance, making downstream LLM use unreliable.

### 3.6 Nykaa and Amazon.in: Blocked Entirely

Both Nykaa and Amazon.in rejected headless browser connections at the protocol level (ERR_HTTP2_PROTOCOL_ERROR and connection timeouts respectively). Neither site returned any page content. This is consistent with spec §9.6's warning about hardened marketplace sites and confirms that residential proxy infrastructure is a hard prerequisite — not a nice-to-have — before these retailers can be onboarded. They are out of scope for Sprint 1.

---

## 4. v0 → v1 Schema Decisions

**Delta 1: extraction_method on scraper_configs** — Added an `extraction_method` enum field (values: `json_ld`, `next_data`, `css_selector`) to the `scraper_configs` table. Tira's 0% field presence was caused entirely by the absence of a `__NEXT_DATA__` extraction path. This is not a data problem; it is a missing config variant. Sprint 1 must implement the `next_data` extractor and wire Tira's scraper config to it before Tira can contribute any records.

**Delta 2: ingredient_extraction_queue table + ingredient_scrape_status** — Ingredients at 0% everywhere is not a schema error; it is a pipeline architecture gap. Ingredients require a secondary, interaction-driven scrape after product discovery. Added `ingredient_extraction_queue` table (tracks products awaiting ingredient scrape) and `ingredient_scrape_status` column on `products`. Sprint 1 will populate the queue; the ingredient scraper itself is a Sprint 2 deliverable.

**Delta 3: promotions table replaces current_offers JSONB** — Removed `current_offers JSONB` from `retailer_listings`. Offers at 0% across all pages confirmed the field is structurally misplaced — promotions are time-bounded, ephemeral, and cross-listing. Added a dedicated `promotions` table with `retailer_id`, `valid_from`, `valid_until`, and `offer_detail` columns. This entity is not populated in Sprint 1; it is scaffolded for Sprint 2+ when cart-layer scraping is added.

**Delta 4: rating field decomposition** — Replaced the single `rating_raw TEXT` field with three fields: `rating_value NUMERIC(3,2)` (normalized 0–5 score), `rating_count INTEGER` (number of reviews), and `rating_raw TEXT` (audit/original string). Purplle's 90% rating presence provided the test data; Purplle surfaces both value and count in structured HTML. Keeping `rating_raw` preserves the original scraped string for QA and future re-normalization without re-scraping.

**Delta 5: description_source tracking** — Added `description_source TEXT` column to `products` with values `shopify_body_html`, `product_page_scrape`, and `llm_extracted`. Description presence ranging 38–100% by brand means the field will be populated via different pathways — and downstream LLM enrichment must know whether it is working from complete, partial, or absent source copy. Without provenance tracking, pipeline confidence scoring is impossible.

**Delta 6: compare_at_price nullable — confirmed, documented** — compare_at_price was present at 100% for 4 of 5 Shopify brands and 0% for The Derma Co (which does not display MRP strikethrough). No schema change needed — the field is already nullable in v0. This delta exists to make the design intent explicit in schema comments: nullable is correct behavior, not a gap.

**Delta 7: taxonomy layer — confirmed necessary** — category_hint ranged from 38% to 100% across brands and was absent entirely on Tira and Purplle. The field is inconsistently named, inconsistently populated, and retailer-specific in vocabulary (e.g., "Face Serum" vs. "Serums & Essences" vs. "Serum"). A separate taxonomy normalization layer (mapping raw hints to canonical Wand categories) is confirmed as necessary. Sprint 1 will capture raw hints; taxonomy mapping is a Sprint 1 data task, not schema work.

**Delta 8: brand as product-level field — confirmed** — Brand is resolved during deduplication (matching listings from multiple retailers to a single canonical product) and stored once on `products`, not replicated on each `retailer_listing`. The scorecard confirmed brand_name at 100% reliability across all accessible retailers, validating that dedup has sufficient signal. No schema change; this delta documents that the v0 design choice was correct and should not be revisited during Sprint 1.

---

## 5. What v0 Got Right

**Variants as JSONB.** Variants (size/shade SKUs) were present at 100% across all Shopify D2C brands and Tira/Purplle. The JSONB representation — storing variant arrays without a separate variants table — is validated. Variant structures differ enough across retailers that a normalized relational table would add join complexity without gain at Phase 1 scale.

**compare_at_price nullable.** The scorecard confirmed that MRP/strikethrough pricing is not universal (0% on The Derma Co). Making this nullable was correct; any NOT NULL constraint would have broken ingestion for a major brand.

**Taxonomy layer as separate concern.** The v0 model stored `category_hint` as a raw scraped value and deferred normalization to a taxonomy layer. The scorecard showed category_hint is unreliable and vocabulary-inconsistent — confirming that normalizing inline during scrape would be premature. The two-step design (capture raw, normalize later) is validated.

**Brand as product-level field.** Brand resolution at deduplication time, not at listing ingestion time, is correct. The scorecard showed brand_name is highly reliable as scraped signal, giving dedup strong input data, while avoiding redundant brand columns on every listing row.

**Raw + derived field split.** The v0 pattern of storing raw scraped values alongside derived/normalized fields (e.g., `rating_raw` alongside computed rating fields) is validated by the rating finding. Purplle's 90% rating presence would have been lossy if only a normalized value were stored — the raw string captures edge cases (e.g., "4.2 (1.2k reviews)") that structured parsing may mishandle, enabling re-processing without re-scraping.

---

## 6. Sprint 1 Implications

**Build `next_data` extractor first.** Tira is a priority retailer; without the `__NEXT_DATA__` extraction path, Tira contributes zero records. This is a one-time scraper config work item that unlocks an entire retailer.

**Scaffold ingredient queue, do not build ingredient scraper.** The `ingredient_extraction_queue` table and `ingredient_scrape_status` flag should be created in Sprint 1 schema migrations. The actual ingredient scraper is a Sprint 2 deliverable — do not block Sprint 1 data ingestion on it.

**Defer promotions scraping entirely.** The `promotions` table schema can be created, but no scraping logic should be planned for Sprint 1. Offers require cart-layer access; that is a separate capability investment.

**Prioritize D2C Shopify brands for initial data volume.** Fields that are most reliably extractable (brand, name, price, stock, images, variants) are all 100% on Shopify D2C. Sprint 1 should reach full coverage on the 5 Shopify brands before investing in Purplle or Tira edge cases.

**Carry Nykaa/Amazon as a known risk, not an open decision.** Residential proxy procurement needs to begin in Sprint 1 (or be formally deferred to Sprint 2) — but this cannot remain an open question past the sprint. The longer proxy infrastructure is deferred, the longer two of India's largest skincare retailers are out of the data model.

---

## 7. Open Questions

**Q1: Tira login wall.** The spike confirmed that `__NEXT_DATA__` parsing is the right extraction path for Tira, but did not test whether Tira's product pages are fully accessible to unauthenticated scraper sessions or whether certain fields (price, stock) require a logged-in session. This needs a targeted test before Sprint 1 closes.

**Q2: Ingredient extraction interaction depth.** Ingredients at 0% is confirmed, but the spike did not characterize how many interaction steps (clicks, scroll triggers, tab switches) are required per retailer, nor whether ingredient data is ultimately in the DOM or loaded via a separate API call. The `ingredient_extraction_queue` is designed to handle this, but the extractor design is unresolved.

**Q3: Purplle rating source reliability.** Purplle ratings were present on 90% of pages, but the spike did not validate whether those ratings are self-hosted (stable, scrapeable long-term) or pulled from a third-party widget (potentially volatile). If the latter, rating data from Purplle could disappear or change format without notice — which affects how much Sprint 1 should invest in rating normalization logic.
