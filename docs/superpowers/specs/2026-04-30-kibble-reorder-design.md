# Kibble Auto-Reorder System — Design Spec
**Date:** 2026-04-30
**Project:** sasank-playground v2 (new repo)

---

## Overview

An end-to-end system that monitors a dog's kibble bin via a BLE Time-of-Flight sensor, forecasts when kibble will run out, automatically finds the best deal across Indian e-commerce retailers, and places the order — with minimal or zero human intervention depending on the user's chosen mode.

Designed to be multi-tenant from day one so the app can expand to other dog owners.

---

## Architecture

```
MokoSmart TOF S02R (BLE)
        │
        ▼
Android App (Kotlin + Jetpack Compose)
  - BLE scanner via MokoSmart Android SDK
  - Kibble level UI + settings
  - Push notifications (FCM)
        │ HTTPS REST API
        ▼
Cloud Backend (Python / FastAPI)
  ├── Sensor ingest & forecasting
  ├── Deal selection engine
  ├── Retailer scraper plugins (Playwright)
  ├── Checkout automation
  └── PostgreSQL + Redis (Celery jobs)
```

**ESP32 future path:** when the user migrates from Android BLE reading to an ESP32 hub, the ESP32 calls the same backend `/ingest` endpoint. The Android app becomes UI-only. No backend changes required.

**Multi-tenant:** each user has their own account, bin config, pincode, preferences, and retailer sessions. The same backend serves all users independently.

---

## Hardware

**Sensor:** MokoSmart TOF S02R (BLE 5.0, Time-of-Flight distance measurement)

**Integration:** Android app scans BLE advertisements using the MokoSmart Android SDK, parses distance readings, and sends them to the backend via REST API.

**Reading schedule:** 4 readings per day (every 6 hours). Configurable in settings. On-demand "Read now" button available in the app for testing and post-refill confirmation.

---

## Bin Calibration & Learning

**Onboarding (one-time):**
- User empties the bin and taps "Set empty level" — stores the distance from sensor to bin bottom
- User enters container capacity in kg (max the bin can hold)

**After 1st refill (any amount):**
- System detects a sudden distance decrease (refill event) but doesn't know the weight added — calibration incomplete

**After 2nd refill (first app-ordered refill):**
- App placed this order, so it knows the exact weight ordered (e.g. 10kg)
- System observes the distance jump, maps cm → kg, fully calibrates the bin
- From this point: shows kg remaining, % remaining, days remaining

**Reorder threshold:**
- User sets "reorder at X%" during onboarding as a starting point
- After full calibration, app recommends adjustments based on actual consumption rate and observed retailer lead times

---

## Android App

### Screens

**Onboarding (one-time):**
1. Account setup: name, email, pincode
2. Dog profile: dog's name, breed, kibble brand and product
3. Container capacity (kg)
4. Empty calibration: empty the bin, tap "Set empty level"
5. Pack size preference: 3kg / 5kg / 10kg / Best value (default — system picks the pack size with the lowest price per kg that fits within container capacity)
6. Reorder threshold: slider to set initial % (e.g. 20%)
7. Payment mode: 90% autonomous (default) or 100% autonomous
8. Retailer session setup: tap to log in to each retailer once via in-app browser
9. Delivery estimate check: enter pincode, see live delivery estimates per retailer

**Home screen:**
- Illustrated kibble bin with animated fill level matching latest sensor reading
- "Last updated: 2h ago" timestamp
- Days remaining estimate + next predicted order date
- Auto-order toggle (quick access)
- BLE connection indicator
- "Read now" button (on-demand BLE read)

**Orders screen:**
- Current best deal card (retailer, price, pack size, delivery estimate)
- Full price comparison table across all retailers including quick commerce (with savings vs. quick commerce highlighted)
- Past order history

**Settings:**
- Reorder threshold % (app surfaces recommendations here over time)
- Payment mode (90% / 100%)
- Pack size preference
- Deal criteria: minimum seller rating, pinned retailer, blacklisted retailers
- Manage retailer sessions (re-login when expired)
- Notification preferences

### BLE Service

Runs as an **Android foreground service** (required for reliable background BLE on modern Android — shows a persistent "Kibble monitor active" notification). Reads the MokoSmart S02R every 6 hours, parses the distance reading via the MokoSmart Android SDK, and POSTs it to the backend.

### Notifications

- *"Kibble at 22% — ~8 days left, order scheduled"*
- *"Order ready: Royal Canin 10kg on Supertails for ₹2,340. Tap to confirm."* (90% mode)
- *"Order placed: Royal Canin 10kg arriving [date] — saved ₹800 vs Blinkit"* (100% mode)
- *"Confirm order: [details] — emergency Blinkit order, standard retailers delayed"*
- *"Time to re-login to Supertails — session expired"*
- *"Tip: based on your consumption, consider updating reorder threshold to 25%"*

---

## Backend

**Stack:** Python, FastAPI, PostgreSQL, Redis, Celery (background jobs), Playwright (scraping + checkout), Firebase Admin SDK (FCM push notifications)

### Modules

**Sensor Ingest & Forecasting**
- Receives distance readings from Android app
- Stores raw readings, computes consumption rate (cm/day → kg/day after full calibration)
- Forecasts run-out date
- Triggers deal-finding Celery job when forecast crosses reorder threshold

**Deal Selection Engine**
- Runs `search()` across all active retailer plugins in parallel
- Applies hard filters (see Deal Selection section)
- Scores by total price per kg (product + shipping, normalized by weight)
- Returns winner; always includes quick commerce listings in comparison output regardless of eligibility

**Retailer Scraper Plugins**
- Each retailer is an isolated Python class with 4 methods: `search()`, `add_to_cart()`, `checkout()`, `get_lead_time()`
- Playwright headless browser, runs entirely on backend
- Adding a new retailer = one new plugin file, nothing else changes

**Checkout Automation**
- Uses the Playwright session from scraping
- 90% mode: completes everything up to payment screen, sends FCM notification, waits for user confirmation, then completes payment (user enters UPI PIN or card OTP manually)
- 100% mode: selects user's pre-loaded Paytm or PhonePe wallet, completes end-to-end silently

**Lead Time Service**
- Three-layer approach:
  1. Baseline hardcoded estimates per retailer × city tier (metro/tier-2/tier-3)
  2. Updated from real order history after each delivery
  3. Real-time check right before placing an order — always fresh, never cached
- In-app delivery estimate tool queries this live; results cached per pincode × retailer for 24 hours

**Forecast Graph Service (Prophet)**
- Uses Facebook Prophet to model kibble level % over time
- Trained on historical sensor readings for the bin, excluding refill events
- Forecasts 30 days forward; outputs predicted level % with upper/lower confidence bands
- Identifies two key dates from the forecast: predicted reorder date (when forecast crosses reorder threshold %) and predicted empty date (when forecast hits 0%)
- Endpoint: `GET /bins/{bin_id}/forecast` — returns historical readings + Prophet forecast series + reorder threshold + predicted reorder date + predicted empty date
- Android app renders this as a time series graph: historical line, forecast line with confidence band, horizontal dashed line at threshold %, vertical markers for reorder date and empty date
- Requires at least 4 readings (1 day of data) to produce a forecast; returns `insufficient_data` status with empty forecast list otherwise
- Android app handles `insufficient_data` gracefully: shows only the historical data points collected so far, hides the forecast line and confidence band, and omits the predicted date markers — no error shown to the user

---

## Retailer Plugins

| Retailer | Type | Notes |
|---|---|---|
| Amazon.in | Standard e-commerce | Anti-bot measures — realistic delays + session cookies required |
| Supertails | Standard e-commerce | Pet-focused, manageable |
| HUFT | Standard e-commerce | Pet-focused, manageable |
| Blinkit | Quick commerce (web) | Emergency fallback + price comparison only |
| Zepto | Quick commerce (web) | Emergency fallback + price comparison only |
| Swiggy Instamart | Quick commerce (web) | Emergency fallback + price comparison only |
| D2C brands (Royal Canin, Drools, Farmina etc.) | Per-brand plugin | Varies per site |
| Custom (user-added) | Price monitoring only | User pastes product URL; price tracked but checkout not automated |

**Login & sessions:** First-time per retailer, app prompts user to log in manually via in-app browser. Session cookies saved encrypted. Subsequent orders use saved session. App detects stale sessions before attempting checkout (not during) and notifies user to re-login. Expected re-login frequency: every 1–3 months per retailer.

**Search parameters:** query string, pincode, weight range (kg). Returns all pack sizes and multi-packs with price per kg calculated for each.

---

## Deal Selection Algorithm

**Step 1 — Hard filters:**
- Real-time lead time > days until run-out → disqualified
- Seller rating < user's minimum threshold (default 4.0★) → disqualified
- Pack size > container capacity → disqualified
- Pack size doesn't match user's fixed preference (if set) → disqualified
- Blacklisted retailer → disqualified
- Quick commerce → excluded from ordering (included in comparison display only)

**Step 2 — Score:**
- Single factor: **total price per kg** (product price + shipping cost, normalized by weight)
- Delivery speed not a scoring factor — lead time intelligence already handles timeliness
- Ties broken by faster delivery

**Manual mode overrides (user-configurable):**
- Minimum seller rating threshold
- Pack size override (one-time or permanent)
- Pin a preferred retailer (always buy here if it passes filters)
- Blacklist retailers

**Safety buffer:**
Reorder is triggered using the **slowest baseline ship date** across all qualifying retailers as the conservative anchor — ensuring the order is placed early enough that even the slowest option would arrive in time. Real-time lead time at order placement confirms the chosen retailer specifically.

**Emergency fallback:**
If no standard retailer can deliver before run-out (all out of stock or delayed):
1. Fall back to quick commerce (Blinkit/Zepto) regardless of price
2. Notify user: *"Standard retailers can't deliver in time — ordering from Blinkit for ₹X instead"*
3. In 90% mode: always requires user confirmation before emergency fallback order

---

## Payment Modes

**90% Autonomous (default):**
Playwright completes full checkout — finds deal, adds to cart, fills in delivery details — then pauses at the payment screen and sends an FCM notification to the user. User taps confirm, is taken to the payment screen (in-app browser or retailer deep link), and enters UPI PIN or card OTP. That is the only manual touch point.

**100% Autonomous (opt-in):**
User pre-loads a Paytm or PhonePe wallet. Playwright selects it at checkout. Order completes silently end-to-end. User receives a post-order confirmation notification only.

**Wallet balance monitoring:**
In 100% mode, backend monitors wallet balance (via Playwright on wallet provider's web app) and sends a low-balance notification before the next forecasted order so the user can top up in time.

No payment gateway (Razorpay etc.) used in v1. All payments flow directly user → retailer. App never handles money. Razorpay considered for v2 when app-level subscription billing is introduced.

---

## Data Model

**users** — id, email, name, pincode, auto_order_enabled, payment_mode, min_seller_rating, pack_size_preference, reorder_threshold_pct, pinned_retailer_id, blacklisted_retailer_ids[], wallet_type, created_at

**dogs** — id, user_id, name, breed

**bins** — id, user_id, dog_id, sensor_device_id (BLE MAC), container_capacity_kg, empty_calibration_distance_mm, full_calibration_distance_mm (nullable, learned after 2nd refill), calibration_state (empty_only / fully_calibrated)

**sensor_readings** — id, bin_id, timestamp, distance_mm, kibble_level_pct (nullable), kibble_kg_remaining (nullable)

**orders** — id, user_id, bin_id, retailer_id, product_name, pack_size_kg, quantity, total_price, shipping_cost, price_per_kg, status (pending/placed/confirmed/delivered/failed), placed_at, estimated_delivery_date, actual_delivery_date, retailer_order_reference, triggered_at_level_pct

**retailer_sessions** — id, user_id, retailer_id, encrypted_cookies, last_refreshed_at, estimated_expiry_at

**retailers** — id, name, base_url, plugin_class, type (standard/quick_commerce/d2c/custom), is_active

**lead_times** — id, retailer_id, pincode, estimated_days, source (baseline/actual_order/realtime_poll), recorded_at

**delivery_estimate_cache** — id, user_id, retailer_id, pincode, result_json, cached_at, expires_at (24hr TTL)

**price_comparison_cache** — id, user_id, product_query, pincode, listings_json (all retailers incl. quick commerce), cached_at, expires_at (24hr TTL)

---

## Out of Scope for v1

- Pattern learning for reading frequency (multi-dog households, irregular feeding)
- Razorpay / credit card subscription billing
- ESP32 hub migration
- Card payment automation (blocked by RBI 2FA mandate)
- Automated checkout for custom user-added retailers (price monitoring only)
