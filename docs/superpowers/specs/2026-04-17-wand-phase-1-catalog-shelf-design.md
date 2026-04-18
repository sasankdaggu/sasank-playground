# Wand — Phase 1 Design: Catalog & Shelf Foundation

**Date:** 2026-04-17
**Status:** Draft — awaiting review
**Author:** Sasank Daggubati (PM) + AI collaborator
**Phase:** 1 of 5 (Catalog + Shelf Foundation)

---

## 1. Overview

**Wand** is an AI-native skincare aggregator for India's Gen Z audience, covering skin, hair, and body care. It aggregates products across marketplaces (Nykaa, Amazon.in, Tira, Purplle) and D2C brand sites (Minimalist, Plum, mCaffeine, Dot & Key, The Derma Co, etc.), surfacing them through a **personal virtual shelf** and a **catalog of specialized AI agents** that analyze every product and the user's whole shelf.

The product's defining idea: **an entourage of AI specialists** (price scout, ingredient checker, dupe hunter, creator-buzz analyst, routine builder, and more) that work continuously on behalf of the user. Agents are first-class objects in a browsable catalog; users install them the way they install apps.

At full capability (Phase 3+), the site can execute purchases across retailers via computer-use browser automation, with the user controlling the payment step.

---

## 2. Positioning

> **"Every product has a panel of AI experts working for you, not for the retailer."**

**Trust moat:** No brand partnerships. No paid placement. Affiliate relationships used where available, but fully disclosed, and the ranking algorithm never weights on commission. Every retailer selling a product is shown — affiliate or not.

**Competitive frame:**

- **vs Nykaa / Tira / Purplle:** they are marketplaces optimizing GMV and bias toward their ad/commerce pipeline. Wand is neutral toward retailers.
- **vs comparison sites (Buywow, BestPrice etc.):** they stop at price. Wand goes deeper — ingredient fit, creator sentiment, dupe analysis, shelf-aware advice.
- **vs generic AI chatbots:** Wand is not a conversation; it's **specialized agents with verdict panels**, grounded in structured product data, not open-ended chat.

**Target user:** India Gen Z (roughly ages 18-28). Mobile-native. Price-conscious but drop-culture-driven. Ingredient-literate. Trusts creators over dermatologists. Expects playful tone, not clinical. Used to app-level polish but also uses web heavily for research and sharing.

---

## 3. Guiding Principles

1. **User side, not retailer side.** Monetary incentives must never bias recommendations. This is the product's primary trust wedge.
2. **Agents are first-class.** Every differentiating behavior of the product is an agent. Agents are browsable, installable, and extensible. New capabilities = new agents, not new code paths in a monolith.
3. **Shelf-first experience.** The user's virtual shelf is the default home screen on every visit. It is the canvas on which agents do their work.
4. **Raw + derived data split.** Every piece of product data has an authoritative raw capture (verbatim from source) and a separate derived layer (LLM-processed, regeneratable). Users can always trace a shown value back to its original source.
5. **Hybrid scraping — cheapest tool that works.** LLMs are expensive; use them only where traditional tools fail. LLMs help locate data on pages; they never hallucinate values into fields where accuracy matters.
6. **Self-healing with a human escape hatch.** Automation is agentic; when it fails repeatedly, the problem becomes a human curator task, not an unbounded LLM bill.
7. **Responsive web, Gen Z aesthetic.** Desktop + mobile web from day 1. Gen Z means bold, playful, themeable, shareable — the shelf must be flex-worthy.

---

## 4. Scope: Phase 1

### In scope

- **Product catalog**: ingestion pipeline for ~15,000–20,000 SKUs at launch across Tier 1 retailers (Nykaa, Amazon.in, Tira, Purplle, + 5-8 D2C brands: Minimalist, Plum, mCaffeine, Dot & Key, The Derma Co).
- **Product detail pages**: hero, price comparison across retailers, stock status, description, ingredient list, "Add to shelf" CTA, passive "Buy" links to retailer URLs.
- **Search & browse**: text search, category filter (skin/hair/body), basic sort.
- **User auth**: phone-OTP-first, guest mode allowed through onboarding until shelf is built.
- **Onboarding flow** (4 steps, ~60s):
  1. Goals (face + hair + body concerns on one screen)
  2. Build your shelf (visual shelf UI, theme picker)
  3. Pick starting agents (3 preselected; full catalog browsable — agent framework itself deferred to Phase 2, but picker UI ships for user commitment)
  4. Save your shelf (phone OTP soft-auth)
- **Virtual shelf**: visual bathroom-shelf UI with themes (Tile default, Night, Neon Pop, Retro, Garden, Pastel), per-product metadata (added date, opened date, % remaining, rating, notes).
- **Price freshness**: hourly refresh for top-5k SKUs, daily for the long tail.
- **Basic user profile**: concerns, budget band (captured progressively), theme preference.
- **Scraping infra**: hybrid pipeline with self-healing selector repair and human review queue.
- **Admin UI**: human review queue for flagged scrapes.

### Out of scope (future phases)

- **Phase 2:** Agent framework, agent catalog browse/install/uninstall, product-level + shelf-level + global agents running on real data.
- **Phase 3:** Computer-use checkout (remote browser automation, user-confirmed payment).
- **Phase 4:** Growth (share cards for shelf, SEO optimization, push notifications, referral).
- **Phase 5:** Affiliate integration + transparency UI, eventual subscription tier.
- **Other deferred:** q-commerce integration (Zepto, Blinkit, Instamart) — Phase 1.5 add-on, roughly 4 weeks after launch.
- **Out for now:** iOS app (unless iOS cohort demands), native Android app, content/editorial, user reviews (UGC), international.

---

## 5. User Experience

### 5.1 Onboarding flow

Four steps, designed to get the user to a built shelf before asking for auth.

**Step 1 — Goals (~20s).** One screen, three groups (Face / Hair / Body), each with concern chips (multi-select). "Not applicable" opts out of a whole area. All skippable.

**Step 2 — Build your shelf (~30s, hero step).** The shelf is presented as a visual bathroom shelf (wooden planks, tile background, post-it labels for each category, plant decor, dashed "+ Add" slots). The user adds products via:
- Search by name
- Barcode scan (Phase 1)
- Upload a photo of their bathroom shelf for CV extraction (Phase 2 feature — show placeholder entry point)

Inline theme picker: Tile (default), Night, Neon Pop, Retro, Garden, Pastel. Theme is stored on the user profile and applied across the whole app.

**Step 3 — Pick your starting agents (~10s).** 3 agents preselected (Price Scout, Ingredient Check, Dupe Hunter). User can toggle, add more from a preview, or browse the full catalog (placeholder — agent framework lives in Phase 2, but the picker UI is present so the user mental model is set). **User's agent selections are persisted to the profile in Phase 1**, so when Phase 2 ships the framework, each user's chosen agents are pre-installed and begin running immediately — no re-onboarding required.

**Step 4 — Save your shelf (~5s).** Phone OTP (+91). "Continue as guest" allowed — shelf persists in a long-lived anonymous session that can be claimed on sign-up.

### 5.2 Landing experience (post-onboarding, every visit)

**The shelf is the home page.** `/shelf` (authenticated). Unauthenticated visitors see a marketing landing + onboarding CTA.

From the shelf, primary nav to:
- Search / browse catalog
- Agent catalog (Phase 2; in Phase 1 this is a "coming soon" placeholder)
- Profile / settings (theme, goals, account)

### 5.3 Product detail page (Phase 1 version)

Passive product info with price comparison — no agent verdicts yet.

Sections:
- Hero: image gallery, title, brand, variant (size/shade), category tags
- **"Available at" table**: retailer rows with price, stock status, last-checked timestamp, Buy button (opens retailer URL in new tab). Cheapest row highlighted.
- Description (with source tag — e.g., "from brand site")
- Ingredient list (parsed, with "See full INCI" link)
- Add to shelf CTA
- Reviews summary (if available via scraping) — simple count + star average; deeper summarization is a Phase 2 agent

The page is designed so Phase 2 agent panels slot in without structural changes — the same data already exists.

### 5.4 Search & browse

- Text search with autocomplete (product name, brand)
- Filters: category (skin/hair/body), subcategory, brand, price range, ingredient presence/absence, rating
- Sort: relevance, price (low to high), rating, newness

---

## 6. Information Architecture

**Primary routes:**

- `/` — marketing landing (unauthenticated) / redirect to `/shelf` (authenticated)
- `/onboarding` — the 4-step flow
- `/shelf` — user's shelf (home page)
- `/search?q=...` — search results
- `/c/<category>` — category browse (skin, hair, body, and sub-categories)
- `/p/<product-slug>` — product detail
- `/agents` — agent catalog (Phase 2; placeholder in Phase 1)
- `/profile` — user settings

**SEO priorities (Phase 1 lays the groundwork, Phase 4 expands):**

- `/p/<slug>` pages are SSR-rendered with full structured data (JSON-LD Product schema) so they can rank for queries like "Minimalist Niacinamide review" and "The Ordinary Niacinamide vs Minimalist".
- Comparison pages, ingredient primers (e.g., `/ingredients/niacinamide`) are Phase 4 growth assets.

---

## 7. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        WEB FRONTEND                             │
│   Next.js SSR/SSG app — responsive (desktop + mobile)           │
│   Pages: Landing, Onboarding, Shelf, Product, Search, Profile   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS / JSON
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API LAYER                               │
│   FastAPI (Python) — REST + server actions                      │
│   Auth (JWT), rate limiting, caching, input validation          │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
  ┌──────────┐       ┌──────────┐      ┌──────────────┐
  │ Postgres │       │  Redis   │      │ Object store │
  │  (core,  │       │ (cache,  │      │   (R2 / S3)  │
  │   price  │       │  queue)  │      │  images,     │
  │ history) │       │          │      │  raw HTML    │
  └──────────┘       └──────────┘      └──────────────┘
       ▲
       │ writes
       │
┌──────┴──────────────────────────────────────────────────────────┐
│              SCRAPING / INGESTION PIPELINE                      │
│   Orchestrator agent → Extraction tier cascade (0-5) →          │
│   Validation → Dedup → Postgres                                 │
│   Repair agent (self-healing) · Quality agent · Human queue     │
│   Scheduled via Temporal (or Celery)                            │
│   Browser Pool: Playwright on remote VMs + residential proxies  │
└─────────────────────────────────────────────────────────────────┘
```

**Rationale for stack choices (single-line why):**

- **Next.js** — SSR for SEO on product pages, first-class responsive, strong ecosystem for Gen Z-aesthetic UI (Tailwind, Radix, Framer Motion).
- **FastAPI (Python)** — Python dominates the LLM/agent ecosystem; scraping pipeline is heavily LLM-adjacent; typed async APIs are ergonomic.
- **Postgres** — single-source-of-truth for products, shelves, users, price history. Use `pg_partman` for price history partitioning.
- **Redis** — cache + queue (Celery broker or Temporal event bus).
- **R2 (Cloudflare) or S3** — product images (hosted + resized via image CDN), archived raw HTML/screenshots for scraper reprocessing.
- **Playwright + remote VMs** — browser automation for scraping; later reused for Phase 3 computer-use checkout.
- **Temporal (preferred) or Celery** — durable workflows. Temporal is purpose-built for long-running scraping pipelines with retries, timers, human-in-loop; worth the learning curve for a multi-year system.
- **Residential proxy vendor** — Bright Data, Smartproxy, or Oxylabs. Required for hardened marketplace sites (Nykaa, Amazon).
- **Hosting** — Vercel for frontend, Railway/Render or AWS ECS for backend + workers, managed Postgres (Neon, Supabase, or RDS).

---

## 8. Data Model (v0 — pending spike validation)

> **v0 means: working hypothesis, likely to evolve.** The first implementation task is a Schema Validation Spike (§11) that stress-tests this model against real scraped data before migrations are written.

### 8.1 Entity diagram

```
┌──────────────┐        ┌──────────────────────┐       ┌───────────┐
│   Brands     │◄───────│      Products        │       │ Retailers │
│  id          │        │  id                  │       │  id       │
│  name        │        │  brand_id            │       │  name     │
│  logo_url    │        │  canonical_name      │       │  base_url │
│  own_site    │        │  category            │       │  scraper_ │
└──────────────┘        │  subcategory         │       │  config   │
                        │  variants (JSONB)    │       └─────┬─────┘
                        │  images (JSONB[])    │             │
                        │  ingredients (rel)   │             │
                        │  description_raw     │             │
                        │  description_summary │             │
                        │  source_of_truth_    │             │
                        │    retailer_id       │             │
                        │  data_freshness      │             │
                        │    (JSONB)           │             │
                        └──────────┬───────────┘             │
                                   │ 1:N                     │
                                   ▼                         │
                        ┌──────────────────────┐             │
                        │  RetailerListings    │─────────────┘
                        │  id                  │       N:1
                        │  product_id          │
                        │  retailer_id         │
                        │  listing_url         │
                        │  current_price       │
                        │  compare_at_price    │
                        │  stock_status        │
                        │  current_offers      │
                        │  last_scraped_at     │
                        │  scraping_confidence │
                        └──────────┬───────────┘
                                   │ 1:N
                                   ▼
                        ┌──────────────────────┐
                        │   RawScrapes         │    (immutable, authoritative)
                        │  id, listing_id      │
                        │  scraped_at          │
                        │  raw_html_snippet    │
                        │    (or S3 ptr)       │
                        │  raw_json_ld         │
                        │  raw_price_string    │
                        │  raw_ingredients_    │
                        │    text              │
                        │  raw_description     │
                        │  raw_offers_text     │
                        │  fetcher_version     │
                        │  tier_used           │
                        └──────────┬───────────┘
                                   │ 1:1
                                   ▼
                        ┌──────────────────────┐
                        │  DerivedData         │    (LLM-processed, regeneratable)
                        │  raw_scrape_id       │
                        │  normalized_price    │
                        │  parsed_ingredients  │
                        │  summary_description │
                        │  extraction_model_v  │
                        │  confidence_score    │
                        └──────────────────────┘

                        ┌──────────────────────┐
                        │   PriceHistory       │    (time-series, partitioned by month)
                        │  listing_id          │
                        │  price, timestamp    │
                        └──────────────────────┘

┌──────────────┐        ┌──────────────────────┐       ┌────────────────┐
│    Users     │◄───────│     ShelfItems       │──────►│   Products     │
│  id          │ 1:N    │  id                  │  N:1  │   (canonical)  │
│  phone       │        │  user_id             │       └────────────────┘
│  email (opt) │        │  product_id          │
│  name        │        │  added_at            │
│  profile     │        │  purchased_from_     │
│   (concerns, │        │    retailer_id       │
│   budget,    │        │  purchase_price      │
│   age_band,  │        │  opened_date         │
│   theme)     │        │  pct_remaining       │
│  created_at  │        │  user_rating         │
└──────────────┘        │  notes               │
                        └──────────────────────┘

┌──────────────┐        ┌────────────────────────────┐
│ Ingredients  │        │   ScraperConfigs /         │
│  id          │        │   RepairQueue /            │
│  inci_name   │        │   HumanReviewQueue         │
│  common_name │        │   (separate schema:        │
│  category    │        │    `scraping`)             │
│  concern_    │        └────────────────────────────┘
│    tags      │
└──────────────┘
```

### 8.2 Key modeling decisions

1. **Products vs RetailerListings split.** One canonical product per real-world SKU. Multiple retailer listings per product (each with its own URL, price, stock, offers). This powers cross-retailer price comparison.

2. **RawScrapes + DerivedData layers.** Every scrape writes an immutable raw record; derived data points back to its raw source. Enables (a) authenticity (traceable to source), (b) reprocessing without re-scraping when prompts improve, (c) audit of extraction errors.

3. **Shelf points to Product (canonical), not RetailerListing.** The user owns a product, not a specific retailer's SKU. `purchased_from_retailer_id` stored as context for restock agent later.

4. **Variants as JSONB.** Multi-axis (size × shade × pack × concentration) varies across categories and brands. Shopify's `option1/option2/option3` maps naturally. Flexible schema without premature normalization.

5. **Stock as enum + raw string.** Normalize to enum (`in_stock`, `low_stock`, `out_of_stock`, `discontinued`) but keep the raw source string (e.g., "Only 2 left!") for display and future signals.

6. **Category via canonical taxonomy layer.** Retailer-provided `product_type` and tags are unreliable. We maintain our own taxonomy and map from: brand-site collection URLs, retailer breadcrumbs, tags, and LLM inference (ambiguous cases queued for curator).

7. **User profile as JSONB.** Concerns, budget, age_band, theme, etc. Iteration-friendly; move to columns only when specific fields prove load-bearing.

8. **Ingredients as first-class relation from Phase 1.** Even without the ingredient agent (Phase 2), we parse and link ingredients now — free for the agent when it ships. Avoids painful backfill.

9. **`source_of_truth_retailer_id` on Products.** Pointer to the retailer whose data is authoritative for non-price fields (description, images, ingredients). Usually the brand site; fallback to marketplace.

10. **`data_freshness_per_field` JSON.** Different fields decay at different rates (price: hourly; ingredients: yearly). A single `updated_at` loses this resolution.

11. **Scraping infra tables in their own schema.** Operational data (configs, queues) should not pollute core product models.

---

## 9. Scraping Architecture

### 9.1 Two distinct pipelines

**Catalog pipeline** (slow-changing) and **Price pipeline** (fast-changing) are separate by design.

| | Catalog pipeline | Price pipeline |
|---|---|---|
| What it captures | Name, brand, images, ingredients, variants, description | Current price, stock, active offers |
| Refresh cadence | Weekly full refresh; on new-SKU discovery | Hourly for top 5k SKUs, daily for 15k long tail |
| Origin locations | Single origin (data doesn't vary by pincode) | Single origin at launch (multi-origin in Phase 1.5 for q-commerce) |
| LLM involvement | OK to be LLM-heavy (messy fields, low volume) | Minimal — LLM finds where the price is; selectors extract the value |
| Cost tolerance | Higher per SKU (low volume) | Must be minimal per check (high volume) |

### 9.2 Tier cascade — cheapest tool that works

| Tier | Tool | Approx cost/1k pages | Use case |
|---|---|---|---|
| 0 | Structured endpoints (Shopify `/products.json`, JSON-LD, sitemaps, affiliate feeds) | ~₹0 | D2C brand sites (most are Shopify), SEO-rich marketplaces |
| 1 | Traditional selector scraper (Playwright + CSS/XPath) | ~₹5 | Stable marketplaces — Nykaa, Tira, Purplle, Amazon |
| 2 | LLM-assisted selector recovery (regenerate selector once, back to Tier 1) | ~₹500 one-off per recovery | Self-healing for any site |
| 3 | LLM extraction on raw HTML (Haiku / Gemini Flash) | ~₹50 | Long-tail D2C sites, ingredient prose |
| 4 | LLM + vision on screenshots | ~₹500 | Ingredient lists in images, offer badges, carousels |
| 5 | Browser-use agent (full navigation, multi-step) | ~₹5k | Phase 3 checkout; Phase 1 only for login-gated content |

### 9.3 The "LLM locates, regex extracts" pattern

For accuracy-critical fields (price, stock), the pipeline separates two phases:

- **Discovery phase** (one-time or after breakage): LLM reads the page, outputs a CSS/XPath selector pointing at the data. Output is a *config*, not a value.
- **Extraction phase** (every scrape): Traditional scraper reads that config, grabs the DOM node, parses with regex. Zero LLM involvement in the hot path. **Zero hallucination risk on price.**

### 9.4 Self-healing with human escape hatch

```
Price extraction fails
  ↓
Selector Repair Agent (LLM regenerates selector from current HTML)
  ↓ validates on 3 sample pages
  ↓ if works: deploy, mark "auto-healed"
  ↓ if fails:
Retry repair (max 3 attempts, ~₹1.50 total cost cap per URL)
  ↓ if still failing:
Human Review Queue
  ↓ curator sees page + last-known-good selector + what agent tried
  ↓ fixes selector OR marks listing unreliable
  ↓ system learns pattern for future repairs
```

Cost is hard-capped per URL. Chronic failures become a human task, not an unbounded LLM bill.

### 9.5 Orchestration agents

- **Scheduler** — prioritizes which SKUs to refresh based on traffic, price volatility, staleness
- **Extraction agents** — one per tier; cascade on failure
- **Selector Repair agent** — self-healing
- **Dedup agent** — merges cross-retailer products via (brand + name + size + shade) fuzzy match, LLM tiebreaker for ambiguous matches
- **Quality agent** — anomaly detection (sudden price drop >50%, missing fields, dedup drift)
- **Human queue** — the one place humans intervene; everything else runs unattended

### 9.6 Anti-bot infrastructure

Marketplaces (Nykaa, Amazon, Tira, Purplle) aggressively block basic requests. Our scraping needs:

- **Residential proxies** (Bright Data, Smartproxy, or Oxylabs) with rotation
- **Playwright-stealth** — mask browser fingerprints
- **Human-like navigation patterns** — dwell times, mouse movement, random scroll
- **CAPTCHA solving** — 2Captcha or hCaptcha solver for occasional hard blocks
- **Request rate limits** per retailer, per proxy IP
- **Session reuse** — maintain cookies across a crawl to reduce captcha triggers

D2C Shopify brand sites require none of this — `/products.json` is open.

### 9.7 Launch retailer list

**Tier 1 (P0, launch):**

- Nykaa
- Amazon.in (enrolled in PA-API via affiliate for structured feed access)
- Tira
- Purplle
- Minimalist (Shopify)
- Plum (Shopify)
- mCaffeine (Shopify)
- Dot & Key (Shopify)
- The Derma Co (Shopify)

**Tier 2 (P1, weeks 8-16):**

- Myntra Beauty, Flipkart
- Remaining top D2C brand Shopify sites
- Sephora India
- **Quick commerce (Phase 1.5):** Zepto, Blinkit, Swiggy Instamart — adds pincode-specific scraping complexity

---

## 10. Cost Model

### 10.1 One-time: catalog ingestion

Per 1,000 SKUs ingested:

| Source type | ₹ per 1k SKUs |
|---|---|
| Shopify `/products.json` (free endpoint) | ₹50–100 |
| Marketplace (JSON-LD + selector + residual LLM) | ₹200–300 |
| Unique D2C sites (Tier 3 LLM) | ₹400–600 |
| Ingredient extraction via vision LLM (~25% of SKUs) | ₹150–250 weighted |
| Cross-retailer dedup + quality check | ₹100–200 |
| Image download + storage setup | ₹50–100 |
| **Weighted blended average** | **~₹700 / 1k** |

**Launch (15–20k SKUs): ~₹10–14k one-time.**

### 10.2 Recurring monthly (20k SKUs under management)

| Component | Monthly cost |
|---|---|
| Price scraping (4.5M checks/mo, traditional selectors + proxies) | ₹10–20k |
| Monthly details re-check (20k SKUs, catalog-grade pipeline) | ₹6–10k |
| New-SKU discovery (daily listing crawl) | ₹1–3k |
| Selector self-healing (bounded LLM repairs) | ₹0.5–2k |
| Human curator queue (~10–20 hrs/mo @ ₹500/hr) | ₹5–10k |
| Infrastructure (Postgres, Redis, R2/S3, VMs, monitoring) | ₹10–15k |
| **Total** | **~₹35–60k / mo** |

**Scaling: ~₹700 × (catalog_size/1k) one-time; ~₹20k fixed + (N_SKUs × ~₹2.5/mo) recurring.**

### 10.3 Quick-commerce addition (Phase 1.5)

Adding Zepto + Blinkit + Instamart with 10-15 pincode coverage: **~₹10–20k/mo extra.** Total Phase 1.5 ≈ ₹50–80k/mo.

---

## 11. First Implementation Task: Schema Validation Spike

Before writing a single migration, **a 1-week spike** to stress-test the v0 data model against real data.

**Goal:** produce a v1 schema grounded in empirical observation, not assumption.

**Activities:**

1. Scrape 5–10 sample products per Tier 1 retailer (~80 samples total) across skin, hair, body categories.
2. Extract every field each retailer exposes. Record presence, format, variance.
3. Produce a **field matrix**: row = field, column = retailer, cell = present/absent/format.
4. Produce a **field-quality scorecard**: which fields are reliably present vs frequently missing vs always-imputed.
5. Identify schema stress points. Known hotspots from initial sampling:
   - Variants (single-axis vs multi-axis)
   - Stock status (boolean vs string)
   - Ingredients (text vs image vs PDF)
   - Category/taxonomy (retailer-specific, unreliable)
   - Offers (unstructured promo strings)
   - Rating (scale, source, UGC aggregation)
6. Write v1 schema with evidence citations per non-obvious decision.
7. Seed database with the sample data to verify queries (price comparison, shelf reads, search).

**Deliverable:** v1 schema + field-quality scorecard + short decision memo (5 pages). Then migrations begin.

---

## 12. Phases Beyond Phase 1 (Context)

| Phase | Horizon | Scope |
|---|---|---|
| **1** | Launch (0-4 months) | Catalog + shelf foundation (this spec) |
| **1.5** | Months 4-5 | Quick-commerce scraping integration |
| **2** | Months 5-10 | Agent framework, agent catalog (browse + install), product-level + shelf-level + global agents running on real data |
| **3** | Months 10-16 | Computer-use checkout (remote browser automation, user controls payment, vaulted credentials gated behind premium tier) |
| **4** | Months 14-20 | Growth: share cards, SEO expansion (ingredient primers, comparison pages), push notifications, referral loops |
| **5** | Months 18+ | Monetization: affiliate integration + full transparency UI, subscription tier unlocking premium agents, potentially agent marketplace (third-party agents) |

---

## 13. Success Criteria for Phase 1

Phase 1 is "done" when:

- [ ] ~15,000 SKUs live across Tier 1 retailers, each with canonical name, brand, category, variants, images, parsed ingredients, and at least 2 retailer listings
- [ ] Price refresh pipeline running hourly for top 5k SKUs, daily for the long tail, with <2% stale-price rate
- [ ] Self-healing repair agent active; human review queue receiving <5% of scrape events
- [ ] User can complete onboarding in under 90s at p90 (target ~60s median: shelf + theme + agents picked + auth)
- [ ] Shelf renders on load in <1s (p90)
- [ ] Product detail page renders in <1.5s (p90) on mobile
- [ ] Search returns results in <500ms (p90)
- [ ] 100 beta users successfully building shelves of 3+ products each
- [ ] No user-visible hallucinations on price (validated against retailer sources weekly)
- [ ] Admin UI operational for the human review queue

---

## 14. Open Questions & Deferred Decisions

- **Product name.** "Wand" is the working name (from onboarding mockup). Final naming is TBD — trademark search, domain availability, Gen Z connotation testing all pending.
- **Search infrastructure.** Phase 1 can use Postgres full-text search; Phase 2+ might need Typesense or Meilisearch. Decide in spike.
- **Image hosting pipeline.** Cloudflare Images vs self-hosted Imgproxy on R2 — decide during build.
- **Analytics stack.** PostHog vs Mixpanel vs Amplitude — decide during build.
- **Domain.** TBD based on naming.
- **Legal review of scraping.** Engage Indian IP/TOS counsel before hardening Nykaa/Amazon pipelines.

---

## 15. Appendix — Brainstorm Empirical Samples

Quick sample of Shopify `/products.json` endpoints during brainstorming (2026-04-17):

- **beminimalist.co/products.json** → ✅ open, 39 products returned, full structured JSON
- **mcaffeine.com/products.json** → ✅ open, 15 products in first page (pagination confirmed required)
- **nykaa.com search page** → ❌ 403 / timeout (anti-bot; requires proxy + stealth)
- **amazon.in search page** → ❌ 503 (anti-bot; requires proxy + stealth)

These confirmed: (a) D2C Shopify brands are near-free to ingest, (b) major marketplaces require the proxy/stealth infra budgeted in §9.6.

Schema insights from samples (incorporated into §8 v0):
- `product_type` from Shopify is unreliable ("Launching", empty string) → canonical taxonomy layer required
- Variants default to single `"Title"`/`"Default Title"` for most Indian D2C; multi-axis is the exception
- `body_html` sometimes empty even on brand sites → page-scrape fallback needed
- `compare_at_price` (MRP) + `price` (selling) is the universal Shopify convention
- `/products.json` paginates; `/collections/<handle>/products.json` is more reliable for category-scoped ingestion

---

**End of Phase 1 design.**
