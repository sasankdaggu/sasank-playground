# Kibble Reorder — Android App Design (Plan 2)

**Date:** 2026-04-30
**Project:** Kibble Auto-Reorder System
**Plan:** 2 of 4 (Android App)
**Backend dependency:** Plan 1 (complete) + new auth, retailer-session, and quiet-hours endpoints added in Plan 2 (see Section 13)

This spec covers the Android client. It assumes the Plan 1 backend is live and all Plan 1 endpoints work as documented in the parent design spec (`2026-04-30-kibble-reorder-design.md`).

---

## 1. Goals

Build a production-quality Android app that:
1. Onboards a new user end-to-end across all 9 setup steps
2. Reads the MokoSmart S02R BLE sensor on a 6-hour cadence and on demand
3. Pushes readings to the backend, observes forecast results, and displays bin status
4. Handles low-stock notifications via FCM
5. Maintains all 9 onboarding steps as functional UI (steps 1–7 fully wired to Plan 1 + Plan 2 auth; step 8 wired to a new Plan 2 retailer-session endpoint; step 9 wired to a Plan 3 endpoint that returns a clear "not yet available" state until Plan 3 ships)
6. Ships with the architectural discipline of a startup-ready codebase: multi-module Gradle, MVVM with unidirectional data flow, strict layering

## 2. Non-Goals

- Order placement UI (Plans 3 and 4)
- Live deal comparison (Plan 3)
- Checkout automation (Plan 4)
- Instrumented UI tests
- iOS or web clients

## 2.5. Brand & Design System

The visual identity is **Deep Botanical** — quiet luxury borrowed from premium tea-brand aesthetics, applied to a pet-care utility. Editorial typography (Noto Serif headlines, Manrope body), forest-green primary against warm-cream surfaces, sage container layers, generous whitespace, no drop shadows, tonal-layer depth instead.

Full design system spec lives at `docs/superpowers/specs/assets/2026-04-30-kibble-design-system.md` and is the authoritative reference for colors, typography, shape, and components.

**Brand wordmark:** "Kibble" set in Noto Serif italic, rendered in Forest Green (#155243) on cream surfaces or Cream (#FCFAF7) on forest immersive headers.

**Tone of copy:** editorial-calm, dog-aware but not childish. Examples:
- Welcome: "Never run out of dog food again."
- Low stock: "Buddy is running low — auto-reorder will arrive Tuesday."
- Empty orders: "Auto-order activates soon. We're learning Buddy's eating pattern."

**Note on Stitch-generated copy:** the design agent's placeholder copy ("Your customized botanical blend...") describes a tea subscription, not dog kibble. All copy in the implementation should be re-written to match the kibble product context while preserving the editorial-calm tone.

## 3. Tech Stack

| Layer | Choice |
|---|---|
| Language | Kotlin 2.0+ |
| Auth | Firebase Auth (email + phone OTP) → Android sends Firebase ID token in `Authorization: Bearer` header → backend verifies via Firebase Admin SDK and resolves to internal `user_id` |
| UI | Jetpack Compose + Material 3 |
| Architecture pattern | MVVM with unidirectional data flow (immutable state + sealed-class intents). Not full redux-style MVI — no central reducer; ViewModels handle their own state transitions. |
| State | Kotlin Coroutines + StateFlow |
| Navigation | Jetpack Navigation Compose |
| DI | Hilt with KSP (not KAPT — KAPT has friction across modules) |
| Networking | Retrofit + OkHttp + Kotlinx Serialization |
| Local database | Room (with Flow returning DAOs) |
| BLE | MokoSmart S02R Android SDK |
| Background | Foreground Service + WorkManager |
| Push | Firebase Cloud Messaging |
| Testing | JUnit 5 for JVM unit tests (ViewModels, Repositories, BLE service logic), MockK, Turbine, MockWebServer, in-memory Room. No instrumented tests in Plan 2. |
| Build | Gradle 8+ with version catalogs (`libs.versions.toml`) and convention plugins in `build-logic/` for shared Compose/Hilt/coroutines config |
| Theming | Material 3 with the **Deep Botanical** design system (`assets/2026-04-30-kibble-design-system.md`). Custom theme — does NOT use Android 12+ dynamic color. Brand identity is consistent across devices. Light + dark mode mandatory. Headlines: Noto Serif. Body/labels: Manrope. Primary: forest green `#155243`. Secondary: sage `#E8F0EA`. Surface: warm cream `#FCFAF7`. Text: deep charcoal `#2D3633`. |
| Accessibility | Content descriptions on all icons, semantic roles on interactive elements, supports system font scaling up to 200% |
| Analytics | `Analytics` interface in `:core:common` with no-op default; concrete implementation deferred (PostHog/Mixpanel) |
| Min SDK | 26 (Android 8.0) — required for stable BLE + foreground services |
| Target SDK | 35 (Android 15) |

## 4. Module Structure

```
:app                     — entry point, Application class, NavHost, Hilt root, bottom nav shell
:core:network            — Retrofit client, KibbleApi interface, auth interceptor, DTOs
:core:database           — Room database, DAOs, entities
:core:ui                 — shared Compose components, Material 3 theme, typography, colors
:core:common             — shared models, Result types, date utilities
:feature:onboarding      — 9-step onboarding flow (screens + ViewModels + state)
:feature:home            — bin dashboard, BLE status, Prophet graph
:feature:orders          — order history + placeholder deal comparison (stubs in Plan 2)
:feature:settings        — all settings screens
:service:ble             — BLE foreground service, MokoSmart SDK integration, sync worker
```

### Dependency Rules

- Feature modules depend on `:core:*` only — never on each other
- `:app` depends on all feature modules to wire navigation
- `:service:ble` depends on `:core:database` (writes readings) and `:core:network` (POSTs readings)
- No circular dependencies
- Each module has its own `build.gradle.kts` with explicit dependencies

### Why Multi-Module From Day One

Single-module is simpler today, but extracting modules out of a monolith later is painful — every cross-feature import becomes a hidden coupling that breaks the moment you split. Establishing module boundaries now is cheap; the build-time and ownership benefits compound as the team grows. This is the explicit "startup-ready" choice from brainstorming.

## 5. State Pattern (MVVM with Unidirectional Data Flow)

Every screen has the same four pieces:

1. **`State`** — immutable data class. All UI state. Example:
   ```kotlin
   data class HomeState(
       val bin: Bin? = null,
       val latestReading: SensorReading? = null,
       val forecast: ForecastResult? = null,
       val bleStatus: BleStatus = BleStatus.DISCONNECTED,
       val isLoading: Boolean = false,
       val error: String? = null,
   )
   ```
2. **`Intent`** — sealed class of user actions:
   ```kotlin
   sealed class HomeIntent {
       data object OnTapReadNow : HomeIntent()
       data class OnToggleAutoOrder(val enabled: Boolean) : HomeIntent()
       data object OnRefreshForecast : HomeIntent()
   }
   ```
3. **`ViewModel`** — receives intents, mutates a `MutableStateFlow<State>`, exposes a read-only `StateFlow<State>`.
4. **Compose screen** — observes state with `collectAsStateWithLifecycle()`, emits intents through a single `(intent: HomeIntent) -> Unit` callback.

This makes every screen read the same way. Code reviews are faster because the shape never varies.

## 6. Navigation

Single Activity (`MainActivity`). Two NavGraph roots:

- **`OnboardingGraph`** — linear 9-step flow. Entry: `OnboardingActivity` is launched from `MainActivity` if `User.onboardingComplete == false`. Each step is its own destination; back stack pops normally; on completion, `User.onboardingComplete = true` is persisted and the user is sent to `MainGraph`.
- **`MainGraph`** — bottom nav with three tabs: Home, Orders, Settings. Each tab has its own nested NavGraph for drill-downs.

The Compose `NavHost` handles all transitions; no manual fragment management. Bottom nav is a Compose `NavigationBar` rendered in `:app`.

## 7. BLE Service

Implemented in `:service:ble` as a started foreground service.

### Lifecycle

- Started by `MainActivity` after onboarding completes
- Survives app being backgrounded
- Persists a "Kibble monitor active" notification (required for foreground service)
- Stops only on user opt-out from Settings or device reboot

### Read Cadence

- WorkManager schedules a periodic `BleReadWorker` every 6 hours
- "Read now" button on Home triggers an immediate one-shot read (sends a broadcast that the service handles)

### Read Flow

1. WorkManager fires → service connects to MokoSmart S02R via the SDK
2. SDK returns distance reading in mm
3. Service writes a `SensorReading` row to Room with `synced=false`
4. Service POSTs to `/bins/{bin_id}/readings`
5. On 200 response, mark row `synced=true`
6. On failure, leave `synced=false`; `SyncWorker` retries on connectivity change

### Why Room as the Bridge

UI never talks to the service. UI observes Room (`Flow<SensorReading>`). Service writes to Room. This decouples the two completely:
- Service can be tested without UI
- UI can be previewed and tested without BLE hardware
- Offline-first: app shows last reading even with no connectivity

## 8. Data Layer

### Network (`:core:network`)

- `KibbleApi` Retrofit interface mirrors backend endpoints
- `AuthInterceptor` reads the current Firebase ID token (refreshing if expired via Firebase SDK) and injects it as `Authorization: Bearer <token>` on every request
- `KibbleApiClient` builds the OkHttp + Retrofit instance
- All DTOs use Kotlinx Serialization
- Repositories convert DTOs to domain models defined in `:core:common`

### Database (`:core:database`)

Entities:
- `User` (id, firebaseUid, email, name, pincode, prefs, onboardingComplete, quietHoursStart, quietHoursEnd, quietHoursTz)
- `Dog` (id, userId, name, breed, kibbleBrand, kibbleProduct)
- `Bin` (id, userId, dogId, capacityKg, calibrationState, emptyMm, fullMm)
- `SensorReading` (id, binId, distanceMm, timestamp, synced)
- `Order` (id, binId, retailer, packKg, priceInr, status, placedAt)
- `RetailerSession` (id, userId, retailer, type, expiresAt, source) — local mirror of backend session metadata; the encrypted blob lives only on the backend. `type` is `cookie | credentials`. `source` is `ONBOARDING | CHECKOUT_PROMPT | SETTINGS_ADD`.

DAOs expose `Flow<T>` queries so screens automatically re-render when data changes.

### Repository Pattern

Each domain area has a repository:
- `UserRepository`, `DogRepository`, `BinRepository`, `ReadingRepository`, `ForecastRepository`, `RetailerSessionRepository`

Repository contract: reads come from Room (instant, offline-capable); writes go to backend first, then Room on success. Network errors surface as a `Result.Failure` for the ViewModel to render. Repositories are the single seam between domain layer and infrastructure.

## 9. Onboarding (9 Steps)

| # | Step | Backend dependency | Plan 2 status |
|---|---|---|---|
| 1 | Account: Firebase login (email/phone OTP) → name + pincode entry | `POST /auth/firebase` (provisions user) → `PATCH /users/me` (name + pincode) | Fully wired |
| 2 | Dog profile: name, breed, kibble brand & product | `POST /users/{id}/dogs` | Fully wired |
| 3 | Container capacity (kg) | `POST /users/{id}/bins` | Fully wired |
| 4 | Empty calibration (tap "Set empty level") | `POST /bins/{id}/calibrate-empty` | Fully wired |
| 5 | Pack size preference (3kg/5kg/10kg/Best value) | `PATCH /users/{id}` | Fully wired |
| 6 | Reorder threshold (slider) | `PATCH /users/{id}` | Fully wired |
| 7 | Payment mode (90% or 100% autonomous) | `PATCH /users/{id}` | Fully wired |
| 8 | **Preferred retailer login only** — pick one preferred retailer + log in (cookies or credentials per retailer policy) | `POST /users/{id}/retailer-sessions` (NEW endpoint added in Plan 2) | Fully wired |
| 9 | Delivery estimate check by pincode (preferred retailer only at this step) | `GET /users/{id}/delivery-estimates` (Plan 3) | UI built; shows "Checking retailers..." then a clear "Delivery info available once Plan 3 is live — tap Skip to continue" state |

### Step 8 Detail — Preferred Retailer Login (Onboarding)

Onboarding asks the user to log into **one** preferred retailer only. Additional retailers are added incrementally at checkout time (see Section 10 — Incremental Retailer Login).

**Flow:**

1. User is shown a list of supported retailers grouped by category:
   - **Marketplace:** Amazon.in
   - **Pet specialists:** Supertails, HUFT
   - **Quick commerce:** Blinkit, Zepto, Swiggy Instamart
   - **D2C brands:** Henlo, Drools direct, Pawlicious, etc.
2. User picks one as their preferred retailer
3. App routes them to the appropriate login flow per retailer category (see below)
4. On success, session is POST'd to `/users/{id}/retailer-sessions`; backend encrypts and stores
5. User proceeds to step 9

### Per-Retailer Login Flow (Hybrid)

Different retailers need different login mechanisms because of their anti-bot postures:

| Retailer category | Login flow | Why |
|---|---|---|
| **D2C brands** (Henlo, Drools, Pawlicious, etc.) | WebView cookie capture | Typically Shopify/WooCommerce — sessions replay reliably from cloud scrapers |
| **Pet specialists** (Supertails, HUFT) | WebView cookie capture | Standard e-commerce stacks; cookies usually portable |
| **Marketplace** (Amazon.in) | Credential entry → server-side login per session | Amazon binds sessions to device fingerprint + IP class; cookie replay fails |
| **Quick commerce** (Blinkit, Zepto, Swiggy Instamart) | Credential entry → server-side login per session | Aggressive anti-bot; cookie replay fails reliably |

**WebView capture:** in-app `WebView` loads the retailer login page. JS bridge reads cookies after successful login. Cookies + retailer name posted to backend. Stored encrypted.

**Credential entry:** native form (email/phone + password). Credentials posted to backend over TLS. Backend stores credentials in encrypted vault (AES-256-GCM with key from env var; same encryption used for session blobs). Scraper logs in fresh per scrape session — never replays a stored cookie. User can revoke credentials any time from Settings.

**Important UX note:** the credential flow needs explicit trust framing — "We'll use these credentials only to check prices and place orders you approve. Stored encrypted. You can revoke any time." Per-retailer consent screen before the credential form.

The new backend endpoint `POST /users/{id}/retailer-sessions` accepts both shapes:
- `{ retailer, type: "cookie", session_blob: <encrypted>, expires_at }`
- `{ retailer, type: "credentials", credentials_blob: <encrypted> }`

D2C order placement also requires login — D2C is "easier on cookies" than Amazon, but D2C scrapers still need authenticated sessions to place orders. Same retailer-sessions table holds both.

## 9.5. Incremental Retailer Login (Plan 4 hook, designed in Plan 2)

The app does not ask users to log into all retailers upfront. Onboarding logs into one preferred retailer; the remaining retailers are added on-demand at checkout time (Plan 4) when the deal-finder discovers a better deal at an unconfigured retailer.

**Why this matters in Plan 2:**
- The onboarding UI must be designed for a single-retailer pick (not a multi-select grid)
- The Settings screen must support adding/removing retailers any time
- Backend endpoint `POST /users/{id}/retailer-sessions` is built once; reused at onboarding and again at checkout time
- The `RetailerSession` Room entity carries a `source: ONBOARDING | CHECKOUT_PROMPT` field to track how each session was captured (useful for future analytics)

**Plan 4 will use it like this** (out of scope for Plan 2, but the seam exists):
> "We found 5kg of [brand] at HUFT for ₹150 less than your default. Log in to HUFT to capture this deal?" → tap → routes through the same per-retailer login flow as onboarding step 8 → session stored → order proceeds.

In Plan 2, the only consumer of this UX is the Settings screen "Add another retailer" button, which exercises the full flow end-to-end.

## 10. Screens

All screens use the **Deep Botanical** design system. Forest-green app bar (`#003a2e`), warm-cream canvas (`#f2fcf7`), sage container cards (`#E8F0EA`), Noto Serif headlines, Manrope body and labels. App bar contains a sage-circle profile icon (left), the "Kibble" wordmark in italic Noto Serif white (center), and a sync indicator with a status dot (right).

Bottom nav: three items (Home / Orders / Settings) in all-caps Manrope label-sm, active item has a sage pill behind the icon.

### Welcome (pre-auth)
- Hero photograph: golden retriever on a cream couch, soft natural light, masked with a 24px corner radius
- Wordmark: "Kibble" in Noto Serif italic, Forest Green
- Headline: **"Never run out of dog food again."** (Noto Serif h1, deep charcoal)
- Primary button: **"Continue with phone"** (filled forest green, all-caps Manrope label-sm)
- Secondary button: **"Continue with Google"** (forest-outlined, all-caps)
- Footer: small Manrope body-sm: *"By continuing, you agree to our Terms of Service and Privacy Policy."*

### Home (the hero screen)

This is the most-viewed surface and the hero of the brand. Two states: **normal** and **low stock / reordering**.

**Layout (top to bottom):**
1. Forest-green app bar (profile · Kibble wordmark · sync indicator)
2. Hero zone (cream canvas):
   - Custom illustrated **kibble container**: tea-canister silhouette with sage body, forest outline (2px), forest lid, sage knob. Fill is forest green (or warm amber when below reorder threshold). Subtle decorative botanical leaves at the corners. Small sensor dot on the underside of the lid.
   - Below container: large numeric percentage in Noto Serif (~56px) — color shifts from Forest Green (normal) to Warm Amber (low stock).
   - Headline (Noto Serif h2): **"About 8 days of food left"** (or "About 4 days of food left" in low state)
   - Subtitle (Manrope body-md, on-surface-variant): **"Next refill projected for Tue, May 8"** (or "Reorder triggered automatically")
3. **Forecast card** (light-sage container `#ecf6f1`, 20px radius, no shadow):
   - **Header row**: label `CONSUMPTION FORECAST` (Manrope label-sm, all-caps, on-surface-variant) on the left; status word in Noto Serif (h3-size, primary forest color in normal state, warning amber in low state) on the right. The status word is a one-glance summary of whether actual consumption is tracking the forecast: **Steady** (matches model), **Falling** (faster than expected), **Climbing** (slower than expected). Computed by comparing the latest 7-day actual slope against the model's expected slope.
   - **Chart**: single smooth editorial line in primary forest green, ~2px stroke, rounded ends. The line is one continuous curve from the user's earliest reading on the left through "today" and into the projection on the right. **No dashed split, no confidence band, no threshold line, no data-point markers.** Subtle 1px vertical axis line on the far left at low opacity.
   - **X-axis row**: three labels in Manrope body-sm, on-surface-muted: leftmost is `Today`, middle is the midpoint date (e.g., `May 4`), rightmost is the projected runout date (e.g., `May 8`). Below the row: a thin 1px separator at 8% forest opacity.
   - **Legend row**: `○ Actual    — Projected` in Manrope body-sm, on-surface-variant. The Actual marker is a small outlined circle; the Projected marker is a short forest line segment.
   - The **insufficient-data variant** still applies: when `< 4 readings`, the line is rendered only for the historical portion, the status word becomes "Learning", and the legend shows only `○ Actual`.
4. **Status row**: sage chip "Sensor connected" with a forest dot · right-aligned "Last reading 2h ago" (Manrope body-sm).
5. **Read now** button (filled forest, full width, all-caps).
6. **Auto-reorder on** toggle row (sage pill background, label all-caps, switch on the right).

**Low-stock variant adds at the top of the main scroll**, just below the app bar:
- Soft amber banner with a "REORDERING" pill: *"Buddy is running low. We're placing a 5kg order from Supertails — arriving Tue, May 8 for ₹1,499."*
- The "Read now" button is replaced by **"View order"** (filled forest).
- Numeric %, container fill, and the now-marker on the chart all turn warm amber.

**Insufficient-data variant** (under 4 readings):
- Forecast card shows the historical line only — no dashed forecast, no confidence band.
- Subtitle becomes: *"We'll start projecting once we have a few more readings."*
- Container illustration still renders if calibration is complete; otherwise shows an empty bin with a "Calibrate to begin" link to settings.

### Orders (Plan 2 stub)
- App bar
- Centered **package illustration** on a sage circular backdrop (24px corner radius, soft tonal-layer feel matching the Deep Botanical aesthetic — cream paper bag with a forest-green ribbon on a sage podium)
- Headline (Noto Serif h2): **"Auto-order activates soon"**
- Body (Manrope body-md): *"We're learning Buddy's eating pattern. As soon as we know your kibble's rhythm, we'll find the best deal and arrange the next refill — right on time."*
- Primary button: **"Manage preferences"** → routes to Settings → Reorder preferences
- Bottom nav (Orders active)

(Stitch's draft used "customized botanical blend" copy borrowed from a tea-brand template — replaced everywhere with the kibble-appropriate copy above.)

### Settings (sectioned list, sage card per section, ample whitespace)

Each section has a Manrope label-sm header in muted text. Sections, in order:

1. **Profile** — row: avatar · name · pincode · edit chevron
2. **Reorder preferences**
   - Slider: "Reorder when **20%** remains" · forest thumb on sage track
   - Pack size preference: segmented control (3kg · 5kg · 10kg · **Best value**)
3. **Payment** — segmented control: **"90% autonomous"** (selected) · "100% autonomous"
4. **Retailers**
   - List of currently configured retailers: row per retailer with logo, name, sign-in type pill (`Cookie` or `Credentials`), expiry, sage check or amber re-login chip
   - **"Add another retailer"** button (forest outlined, full width)
   - Tapping a retailer opens a row detail with "Re-sign in" and "Remove" actions
5. **Notifications**
   - Toggle: "Quiet hours **10pm–8am IST**" (default ON)
   - Time-range picker for the quiet window
   - Toggle for low-stock alerts (default ON)
   - Toggle for sensor-disconnected alerts (default ON)
6. **About** — version, terms, privacy
7. **Sign out** — error-color row, single tap (with confirmation sheet)

### Add Retailer (bottom sheet from Settings or Plan 4 "better deal found" prompt)
- Sheet title (Noto Serif h3): **"Add a retailer"**
- Subtitle (Manrope body-md, muted): *"Sign in once. We'll save it securely so we can find deals for you."*
- Cards grouped under Manrope label-sm headers:
  - **Pet specialists** — Supertails · HUFT (`Cookie sign-in` pill)
  - **Marketplace** — Amazon.in (`Credentials sign-in` pill)
  - **Quick commerce** — Blinkit · Zepto · Swiggy Instamart (`Credentials sign-in` pill)
  - **D2C brands** — Henlo · Drools · Pawlicious (`Cookie sign-in` pill)
- Each card: retailer logo, name, sign-in type pill, chevron right
- A sage outlined ring around the user's currently-preferred retailer

### Onboarding screens (9 steps, full-screen each)

All onboarding screens share a common chrome:
- Forest-green app bar with **"Setting up Kibble"** label and a step indicator (e.g., "Step 4 of 9")
- Cream canvas
- Headline (Noto Serif h2)
- Body or input (Manrope)
- Primary button at the bottom (filled forest, all-caps, "Continue")
- Optional Skip link below for the few steps that allow skip

Per-step copy:

1. **Welcome / Sign-in** — see Welcome screen above. After Firebase login, profile entry.
2. **Profile** — Headline: *"Hello! What should we call you?"* · Inputs: full name, pincode (validates Indian PIN format)
3. **Tell us about your dog** — Headline: *"Who are we feeding?"* · Inputs: dog name, breed (optional autocomplete), kibble brand (autocomplete), kibble product (free text)
4. **Container size** — Headline: *"How big is your kibble bin?"* · Slider 1–25 kg with the selected value rendered in large Noto Serif. Default 10kg.
5. **Calibrate empty** — Headline: *"Let's calibrate your bin."* · Body: *"Empty your kibble bin completely, then place the sensor on the inside of the lid."* · Illustration: hand placing a small white sensor disc on the underside of a cream container lid (sage backdrop, soft outline). · Primary: **"Set empty level"** · Skip link: *"I'll do this later"*
6. **Pack size preference** — Headline: *"Which pack size suits you?"* · Cards: 3kg · 5kg · 10kg · **Best value** (auto-recommended) · Body under each: rough monthly cost estimate
7. **Reorder threshold** — Headline: *"When should we reorder?"* · Slider with thumb showing percentage and a dynamic line: *"We'll order when about 4 days of food remains."* · Default 20%.
8. **Pick your preferred retailer** — Headline: *"Where do you usually shop?"* · Card grid (same component as Add Retailer sheet) with single-select. Selecting a card opens the appropriate sign-in flow (cookie WebView or credential form).
9. **Delivery estimate** — Headline: *"Last step — checking delivery to **560001**."* · Body: *"This may take a moment."* · While Plan 3 endpoint is unavailable: shows an editorial-styled deferred state ("We'll confirm delivery details when your first reorder is placed.") · Primary: **"Finish setup"**.

### Per-retailer login flows (used in step 8 and Add Retailer)

**Cookie capture (D2C / Supertails / HUFT):**
- Bottom sheet appears with "Sign in to **Supertails**" title
- Embedded WebView pointed at the retailer's login page
- After successful login, a JS bridge captures the session and the sheet closes with a sage success toast: *"Signed in to Supertails."*

**Credential entry (Amazon / quick commerce):**
- Native sage card with retailer logo
- Body (Manrope body-md): *"We'll use these credentials only to check prices and place orders you approve. Stored encrypted. You can revoke any time from Settings."*
- Inputs: email/phone, password (masked, with reveal toggle)
- Primary: **"Sign in to Amazon"**
- Secondary: **"Cancel"**

### Push notifications
- App icon: solid forest-green circle with a single cream kibble-piece glyph (oval with a soft notch)
- Title (system bold): "Kibble"
- Body for low stock: *"Buddy is at 12% — about 4 days of food left."*
- Body for sensor disconnect: *"We haven't heard from your sensor in 24 hours. Tap to troubleshoot."*

### Empty / loading / error states (consistent treatment)
- All empty states: centered illustration on sage circle, Noto Serif headline, Manrope body, primary call-to-action
- Loading: forest-on-cream linear progress bar at the top of the screen + skeleton sage cards in the body
- Errors: amber banner at the top with a "Try again" link; never a destructive red unless the user is about to lose data

## 11. Notifications (FCM)

In Plan 2, two notification types are wired:

- **Low-stock alert** — triggered server-side when a forecast crosses the user's reorder threshold. Body: "Your kibble is at 18% — Buddy has ~5 days left."
- **BLE connection lost** — triggered locally if the foreground service can't reach the sensor for 24 hours. Body: "Sensor not responding — tap to troubleshoot."

Order-related notifications (placed, shipped, delivered) are deferred to Plan 4.

### Quiet Hours (India default)

Default quiet window: 10pm–8am IST. Notifications scheduled within this window are deferred to 8am the next day. Settings exposes a per-user override. Backend honors the user's `quiet_hours_start` and `quiet_hours_end` fields; on-device fallback if backend doesn't yet support it.

## 12. Testing Strategy

| Layer | Tooling | Target |
|---|---|---|
| ViewModels | JUnit 5 + Turbine + MockK | Every intent → state transition |
| Repositories | JUnit 5 + in-memory Room + MockWebServer | Happy path + network failure paths |
| DAOs | androidx.room.testing | Schema migrations + queries |
| BLE service | JUnit 5 + fake MokoSmart SDK + in-memory Room | Scheduling, parsing, sync retry |
| Compose previews | Compose `@Preview` | Visual sanity per screen |
| Instrumented UI tests | None in Plan 2 | Add Maestro flows in a later plan |

Coverage target: 80% on ViewModels and Repositories. BLE service tests must cover both success and failure paths (no signal, malformed reading, network down during sync).

## 13. New Plan 2 Backend Work

The Android app needs new backend endpoints that weren't in Plan 1:

### Authentication

**`POST /auth/firebase`**
- Body: `{ firebase_id_token: string }`
- Response: `200` with `{ user_id, is_new_user }`
- Backend verifies the Firebase ID token via Firebase Admin SDK; on first login, provisions a new `users` row keyed by Firebase UID; returns the internal `user_id`. Subsequent calls resolve the same `user_id`.
- Adds `firebase_uid` column to `users` table (nullable for backward compat with existing rows from Plan 1; migration provided).
- All other endpoints now require `Authorization: Bearer <firebase_id_token>` header. A FastAPI dependency verifies the token and injects the resolved `user_id` into the request — replacing the path-parameter `user_id` pattern from Plan 1 where appropriate. (Existing `POST /users` from Plan 1 is removed/replaced; user provisioning now happens on first Firebase login.)

### Retailer sessions

**`POST /users/{user_id}/retailer-sessions`**
- Body for cookie capture: `{ retailer: string, type: "cookie", session_blob: string (encrypted), expires_at: ISO8601 }`
- Body for credential entry: `{ retailer: string, type: "credentials", credentials_blob: string (encrypted) }`
- Response: `201` with `{ id, retailer, type, expires_at? }`
- Storage: new `retailer_sessions` table (id, user_id, retailer, type, encrypted_blob, expires_at?, source, created_at, updated_at)
- Encryption: server-side AES-256-GCM with a key from env var (`RETAILER_SECRET_KEY`)
- `source`: enum `ONBOARDING | CHECKOUT_PROMPT | SETTINGS_ADD` for analytics

**`GET /users/{user_id}/retailer-sessions`**
- Returns list of `{ retailer, type, expires_at, is_expired }` for Settings screen rendering. Never returns the encrypted blob.

**`DELETE /users/{user_id}/retailer-sessions/{retailer}`**
- Revokes a stored session/credential. Used by Settings → "Remove retailer."

### User preferences

**`PATCH /users/{user_id}/quiet-hours`**
- Body: `{ start: "HH:MM", end: "HH:MM", timezone: string }`
- Used by Settings → notification preferences. Backend honors these when scheduling FCM low-stock alerts.

These endpoints + the new tables + Alembic migrations are part of Plan 2's scope, executed in the backend repo (`/Users/sdagguba/kibble-reorder/backend`).

## 14. Risks and Open Questions

### Resolved decisions

- **Auth: Firebase Auth.** Android handles email + phone OTP via Firebase. App sends Firebase ID token in `Authorization: Bearer` header. Backend verifies via Firebase Admin SDK and resolves to internal `user_id`. Plan 1 user-provisioning endpoint is replaced by `POST /auth/firebase` which provisions on first login.
- **Retailer sessions: hybrid + incremental.** Cookie capture for D2C and pet specialists (Shopify-backed, replay reliably). Credential entry for Amazon and quick commerce (anti-bot binds sessions to device + IP). Onboarding asks for one preferred retailer only; remaining retailers added incrementally at checkout time when a better deal is found elsewhere.

### Operational

- **MokoSmart SDK quality:** unknown until integration begins. If the SDK is unstable, fallback is the Android `BluetoothLeScanner` API directly with manual GATT parsing.
- **WebView cookie capture per retailer:** each retailer's login flow differs (some use OAuth redirect, some have anti-bot). Step 8 needs per-retailer adapters in `:feature:onboarding`.
- **FCM topic vs. token:** Plan 2 will use device tokens (one-to-one). Topic-based broadcast is YAGNI for a personal app.
- **Plan 3 endpoint contract:** step 9's delivery-estimate response shape must be agreed at Plan 3 time so the Android UI doesn't need a rewrite.
- **Hilt scoping across modules:** every `@HiltViewModel` must be in a feature module that includes the Hilt Gradle plugin; `:core:*` modules expose `@Module @InstallIn(SingletonComponent::class)` bindings.

## 15. Plan 2 Definition of Done

- Firebase Auth integrated; new users provision via `POST /auth/firebase`; all backend calls authenticated
- All 9 onboarding steps render and progress; steps 1–8 are fully functional (step 8 = preferred retailer login only, with hybrid cookie/credential flow per retailer category); step 9 shows its "available after Plan 3" state cleanly
- BLE service reads sensor every 6 hours and on demand
- Home shows real bin %, last reading time, forecast graph, BLE status
- Orders renders the stub state without errors
- Settings persists all preferences via backend, supports adding/removing retailers via the same login flow as onboarding
- FCM notifications fire for low stock and BLE timeout, honoring quiet hours
- Light + dark theme both render correctly
- Basic accessibility: all icons have content descriptions; system font scaling works to 200%
- All ViewModels and Repositories have unit tests; coverage ≥ 80%
- Modules build independently: `./gradlew :feature:home:test` works
- New backend endpoints (`/auth/firebase`, `/retailer-sessions`, `/quiet-hours`) deployed and tested
- App installs on a physical Android device and connects to a real MokoSmart S02R
