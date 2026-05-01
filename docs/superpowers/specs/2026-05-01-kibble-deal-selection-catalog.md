# Kibble Deal Selection & Product Catalog — Design Spec
**Date:** 2026-05-01
**Project:** kibble-reorder v2

---

## Overview

When the forecast crosses the user's reorder threshold (REORDER_NOW state), the backend automatically finds the best kibble deal across all connected Indian e-commerce retailers and sends the user an FCM notification with a one-tap deep link to complete the purchase.

Underpinning this is a global product catalog: a monthly-scraped database of all dog kibble products across all retailers, with daily price/stock refresh. The catalog also powers the onboarding product picker — users select their dog's specific kibble from a searchable list rather than typing free text.

Checkout automation (Playwright, 90%/100% payment modes) is **out of scope** for this plan and handled separately.

---

## Architecture

```
Celery Beat (monthly)   →  Catalog Scraper  →  products + product_listings
Celery Beat (daily)     →  Price Refresher  →  product_prices
Forecast → REORDER_NOW  →  Deal Selector    →  pending_deals + FCM notification
Android                 →  Product Picker   →  Dog.product_id
Android                 →  Orders Screen    →  pending_deals + price comparison
```

---

## Data Model

### New Tables

**`products`** — global shared catalog of kibble products
```sql
id              UUID PRIMARY KEY
brand           TEXT NOT NULL         -- "Royal Canin"
name            TEXT NOT NULL         -- "Maxi Adult"
category        TEXT NOT NULL         -- "dry" | "wet" | "treat"
canonical_name  TEXT NOT NULL UNIQUE  -- normalized: "royal-canin-maxi-adult"
image_url       TEXT
created_at      TIMESTAMPTZ
updated_at      TIMESTAMPTZ
```

**`product_listings`** — one row per (product × retailer × pack size)
```sql
id                   UUID PRIMARY KEY
product_id           UUID FK → products
retailer_id          UUID FK → retailers
retailer_product_url TEXT NOT NULL
retailer_product_id  TEXT             -- retailer's internal SKU/ASIN
pack_size_kg         FLOAT NOT NULL
title                TEXT             -- retailer's raw listing title
image_url            TEXT
is_active            BOOLEAN DEFAULT true
last_catalogued_at   TIMESTAMPTZ
```

**`product_prices`** — append-only price snapshots (30-day retention)
```sql
id            UUID PRIMARY KEY
listing_id    UUID FK → product_listings
price         FLOAT NOT NULL
shipping_cost FLOAT NOT NULL DEFAULT 0
seller_rating FLOAT
in_stock      BOOLEAN NOT NULL
scraped_at    TIMESTAMPTZ NOT NULL
```
Index: `(listing_id, scraped_at DESC)` for fast latest-price lookup.

**`pending_deals`** — winning deal awaiting user action
```sql
id                UUID PRIMARY KEY
bin_id            UUID FK → bins
user_id           UUID FK → users
listing_id        UUID FK → product_listings
price_snapshot_id UUID FK → product_prices
status            TEXT DEFAULT 'pending'  -- pending | acted | expired
deep_link_url     TEXT NOT NULL
comparison_json   JSONB    -- all retailers' prices at selection time (incl. QC)
created_at        TIMESTAMPTZ
expires_at        TIMESTAMPTZ  -- 24hr TTL; expired → re-run on next ingest
```

### Modified Tables

**`dogs`** — add `product_id UUID FK → products` (nullable; set during onboarding)

**`users`** — add two columns:
- `pinned_retailer_id UUID FK → retailers` (nullable; always buy here if it passes filters)
- `blacklisted_retailer_ids UUID[]` (default empty; retailers excluded from deal selection)

**`retailers`** — `retailer_type` values: `"standard"` | `"quick_commerce"` | `"d2c"`

---

## Retailer Plugins

### Data Classes

```python
@dataclass
class CatalogListing:
    name: str
    brand: str
    pack_size_kg: float
    url: str
    image_url: str | None
    retailer_product_id: str | None

@dataclass
class PriceResult:
    price: float
    shipping_cost: float
    seller_rating: float | None
    in_stock: bool
    lead_time_days: int | None   # None = unknown; use baseline from lead_times table
```

### Abstract Base

```python
class RetailerPlugin(ABC):
    retailer_slug: ClassVar[str]   # e.g. "supertails"
    retailer_type: ClassVar[str]   # "standard" | "quick_commerce"

    async def catalog_search(
        self,
        query: str,
        page: Page,
    ) -> list[CatalogListing]:
        """Scrape product catalog entries matching query."""

    async def get_price(
        self,
        listing_url: str,
        pincode: str,
        page: Page,
    ) -> PriceResult:
        """Scrape current price, stock, shipping, seller rating, and lead time."""

    async def get_deep_link(self, listing_url: str) -> str:
        """Return mobile web URL or app deep link (intent://) for the product page."""
```

### Plugins in This Plan — Pilot (3 fully implemented)

| Plugin file | Retailer | Type | Notes |
|---|---|---|---|
| `supertails.py` | Supertails | standard | Shopify-based, first pilot |
| `huft.py` | Heads Up For Tails | standard | Shopify-based, second pilot |
| `amazon_in.py` | Amazon.in | standard | Anti-bot delays, session cookies required |

### Plugins in This Plan — Stubs (return empty results; implemented post-launch)

| Plugin file | Retailer | Type |
|---|---|---|
| `flipkart.py` | Flipkart | standard |
| `petsworld.py` | Petsworld | standard |
| `zigly.py` | Zigly | standard |
| `justdogs.py` | Justdogs | standard |
| `blinkit.py` | Blinkit | quick_commerce |
| `zepto.py` | Zepto | quick_commerce |
| `swiggy_instamart.py` | Swiggy Instamart | quick_commerce |
| `bigbasket.py` | BigBasket | quick_commerce |

All plugins live at `app/services/retailer_plugins/<slug>.py`.

A registry at `app/services/retailer_plugins/__init__.py` maps `retailer_slug → plugin class`. The scraper and deal engine import from the registry — new retailer = one new file.

---

## Catalog Scraper

**Celery beat schedule:** monthly (1st of each month, 02:00 UTC)

**Job:** `tasks.refresh_catalog()`

**Process:**
1. For each active retailer in the DB: instantiate its plugin
2. Run `catalog_search()` with a fixed set of category queries:
   - `"dog dry food"`, `"dog wet food"`, `"dog kibble"`, `"Royal Canin dog"`, `"Drools dog"`, `"Farmina dog"`, `"Pedigree dog"`, `"Purina dog"`, `"Hills dog"`, `"Arden Grange dog"`
3. For each result: compute `canonical_name = slugify(brand + name)`, upsert `products` (on canonical_name), upsert `product_listings` (on retailer_id + retailer_product_url), set `last_catalogued_at = now()`
4. After all retailers complete: mark listings where `last_catalogued_at < now() - 60 days` as `is_active = false`

**Playwright sessions:** catalog scraper runs with cookies from `RetailerSession` for retailers that require login. Retailers without a stored session are scraped anonymously (sufficient for catalog).

**Parallelism:** retailers scraped concurrently (one Playwright page per retailer), up to 4 at a time.

---

## Price Refresher

**Celery beat schedule:** daily (03:00 UTC)

**Job:** `tasks.refresh_prices()`

**Process:**
1. Fetch all `product_listings` where `is_active = true`
2. Group by retailer
3. For each retailer: run `get_price()` concurrently (max 5 at a time per retailer)
4. Insert new `product_prices` row for each result
5. Delete `product_prices` rows older than 30 days

**On-demand refresh at deal-selection time:** the deal selector always runs a fresh `get_price()` for the user's specific product listings immediately before scoring — never relies on the daily cached snapshot for the final decision.

---

## Deal Selection Engine

**Trigger:** `POST /bins/{bin_id}/ingest` → after storing reading, if `forecast_state == REORDER_NOW` and no active `pending_deal` for this bin → enqueue `tasks.run_deal_selection(bin_id, user_id)`

**Job:** `tasks.run_deal_selection(bin_id, user_id)`

### Step 1 — Resolve product and listings
- Load `Dog` for this bin's user → `product_id`
- If `product_id` is null → skip (user hasn't set up product yet)
- Load all active `product_listings` for `product_id`

### Step 2 — Fresh price scrape
- Run `get_price()` for each listing in parallel (max 5 concurrent)
- Insert results as new `product_prices` rows

### Step 3 — Compute days until run-out
- Load latest `ForecastResult` for the bin
- `days_until_runout = (predicted_empty_date - today).days`

### Step 4 — Hard filters (disqualify if any fail)
| Filter | Condition |
|---|---|
| Lead time | `lead_time_days >= days_until_runout` |
| Seller rating | `seller_rating < user.min_seller_rating` |
| Pack size | `pack_size_kg > bin.container_capacity_kg` |
| Out of stock | `in_stock == false` |
| Blacklisted | retailer in `user.blacklisted_retailer_ids` |
| Quick commerce | `retailer_type == "quick_commerce"` (excluded from ordering) |

### Step 5 — Score
- `score = (price + shipping_cost) / pack_size_kg` (price per kg, lower is better)
- Ties broken by `lead_time_days` ascending (faster wins)
- If user has `pinned_retailer_id` and that retailer passes filters → use it regardless of score

### Step 6 — Emergency fallback
If all standard retailers are disqualified (out of stock or lead time too long):
- Re-run with quick commerce listings only
- Winner requires user confirmation regardless of payment mode (notification flags it as emergency)

### Step 7 — Save and notify

Save to `pending_deals`:
```python
PendingDeal(
    bin_id=bin_id,
    user_id=user_id,
    listing_id=winner.listing_id,
    price_snapshot_id=winner.price_snapshot_id,
    status="pending",
    deep_link_url=plugin.get_deep_link(winner.listing_url),
    comparison_json=[  # shape of each entry:
        {
            "retailer_name": str,
            "listing_id": str,
            "price": float,
            "shipping_cost": float,
            "price_per_kg": float,
            "pack_size_kg": float,
            "in_stock": bool,
            "lead_time_days": int | None,
            "retailer_type": str,
            "disqualified": bool,
            "disqualify_reason": str | None,
        }
        # one entry per listing scraped, incl. QC
    ],
    expires_at=now() + timedelta(hours=24),
)
```

Send FCM notification:
```
Title: "Kibble running low — best deal found"
Body:  "Royal Canin 10kg on Supertails · ₹2,340 (saves ₹810 vs Blinkit)"
Data:  { type: "deal_ready", bin_id: "...", deal_id: "..." }
```

### Step 8 — Expiry handling
If `pending_deal.expires_at` is past when the next ingest arrives and state is still REORDER_NOW → delete stale deal and re-run selection.

---

## Backend API Additions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/products?q={query}&limit=20` | Product search for onboarding picker |
| `GET` | `/products/{product_id}` | Product detail + listings summary |
| `PATCH` | `/dogs/{dog_id}` | Update `product_id` after user picks from catalog |
| `GET` | `/bins/{bin_id}/deal` | Current pending deal + comparison table |
| `POST` | `/bins/{bin_id}/deal/acted` | Mark deal as acted (user tapped "Order Now") |

---

## Android UI

### Onboarding — Product Picker (replaces free-text kibble fields)
- Step 2 (dog profile): after entering dog name and breed, show a searchable product picker
- User types brand/product name → calls `GET /products?q=...` → shows scrollable list with product image, brand, name
- Tapping a product sets `Dog.product_id`
- "Can't find your kibble?" fallback → free-text entry (stores brand+name only, no product_id)

### Orders Screen (new screen in bottom nav)
- **Deal card** (shown when pending deal exists):
  - Retailer logo + name
  - Product name + pack size
  - Price + price per kg
  - Estimated delivery
  - "Order Now" button → opens `deep_link_url` in in-app browser / system browser
  - "Dismiss" → marks deal expired, re-runs on next ingest
- **Price comparison table** (always shown when deal data available):
  - All retailers sorted by price/kg
  - Quick commerce shown with "⚡ Express" badge
  - Savings vs. most expensive highlighted in green
- **Past orders** (scrollable list below): order history from `orders` table

### Settings — Connected Retailers
Matches the reference images provided:
- Bottom sheet: "Add a retailer" — list of all supported retailers with logo, name, tagline, "+ Add" button
- Connected state: retailer row shows green "Connected ✓"
- "+ Add another retailer" dashed button at bottom
- Tapping "+ Add" → opens in-app browser to retailer login page → on successful login, session cookies saved via `POST /users/{id}/retailer-sessions`

---

## Celery Infrastructure

**Broker:** Redis (already in docker-compose)

**New tasks:**
- `tasks.refresh_catalog()` — monthly beat
- `tasks.refresh_prices()` — daily beat  
- `tasks.run_deal_selection(bin_id, user_id)` — triggered by ingest

**Playwright in Celery workers:** workers run with `PLAYWRIGHT_BROWSERS_PATH` pointing to pre-installed Chromium. Each task opens a fresh Playwright context, uses cookies from `RetailerSession` where available, closes on completion.

---

## Out of Scope for This Plan

- Playwright checkout automation (90%/100% payment modes) — separate plan
- Wallet balance monitoring — separate plan
- Custom user-added retailer URLs — separate plan
- D2C brand direct sites (Royal Canin, Drools etc.) — added to retailer list post-launch
- Flipkart, Petsworld, Zigly, Justdogs, Blinkit, Zepto, Swiggy, BigBasket plugin implementations: supertails.py, huft.py, amazon_in.py are the three pilot plugins built in this plan; remaining plugins are stubbed (return empty results) and completed post-launch
