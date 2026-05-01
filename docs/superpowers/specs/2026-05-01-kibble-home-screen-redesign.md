# Kibble Home Screen Redesign — Spec

**Date:** 2026-05-01
**Plan:** Plan 4 of the kibble auto-reorder system

---

## Goal

Replace the current home screen's Deep Botanical editorial design (Steady/Falling/Climbing status words, single-curve chart) with a forecast-state-driven design where a single `ForecastState` drives the container fill color, the chart badge, the subtitle text, and the chart appearance — giving average users a clear action signal and curious users a meaningful forecast chart.

---

## Forecast State Model

A single enum `ForecastState` drives all visual output on the home screen. The backend computes it and returns it in the forecast response. The Android app renders it — no state logic on the client.

### States and triggers (evaluated in priority order)

| Priority | State | Trigger |
|---|---|---|
| 1 | REORDERED | Active order exists with status pending / placed / shipped for this bin |
| 2 | REORDER_NOW | `level_pct ≤ reorder_threshold_pct` |
| 3 | REORDER_SOON | `predicted_reorder_date ≤ today + avg_lead_time_days + 1 day buffer` |
| 4 | STOCKED | All other cases |

### Insufficient data fallback (< 4 readings)

`predicted_reorder_date` is unavailable so REORDER_SOON cannot be computed. State collapses to:

| Trigger | State |
|---|---|
| Active order exists | REORDERED |
| `level_pct ≤ reorder_threshold_pct` | REORDER_NOW |
| `level_pct > reorder_threshold_pct` | STOCKED |
| No reading at all | STOCKED (with "connect sensor" subtitle) |

### Lead time lookup (for REORDER_SOON threshold)

`avg_lead_time_days` is sourced from the `lead_times` table keyed by `(retailer_id, pincode)`. If no rows exist for the user's pincode, fall back to city-tier baselines:

- Metro pincode: 2 days
- Tier-2 city: 4 days
- Tier-3 / rural: 7 days

Pincode comes from the user's profile. City-tier mapping uses a static lookup table of Indian pincodes.

---

## Android Visual Layer

### Container fill color

The `KibbleContainer` composable receives a `fillColor` parameter. It changes per state:

| State | Color |
|---|---|
| STOCKED | Forest green (`#155243`) |
| REORDER_SOON | Orange (`#E07B39`) |
| REORDER_NOW | Red (`#C0392B`) |
| REORDERED | Blue (`#2C6FA6`) |

### Subtitle (line below the percentage)

Dynamically composed from forecast data. `[dog name]` is the dog's name from Room.

| State | Sufficient data | Subtitle |
|---|---|---|
| STOCKED | yes | "[Dog name]'s food lasts until [empty date]" |
| STOCKED | no | "Plenty of food · forecast building" |
| REORDER_SOON | yes | "Order by [reorder_window.start] to avoid running out" |
| REORDER_NOW | — | "Running low — reorder now" |
| REORDERED | — | "Order arriving [estimated_delivery_date]" |
| No reading | — | "Connect sensor to get started" |

### Forecast chart redesign

The current single-line chart is replaced with a chart matching the design mockups:

**Always present:**
- Filled area under the line (state color at 20% opacity)
- Vertical dashed "Today" line with date label ("Today\n[date]")
- Horizontal dashed threshold line labeled "Threshold" at `reorder_threshold_pct`
- X-axis labels: "Last refill\n[date]" at left, intermediate date ticks, "Run out\n[date]" at right (or "Run out\n—" when unknown)
- Y-axis: 0% to 100%

**Historical segment:** solid line + fill, one point per reading
**Forecast segment:** dashed line + lighter fill, Prophet output

**Callout box (top-right of chart area):**
- STOCKED / REORDER_SOON / REORDER_NOW: "Recommended reorder window\n[start] – [end]" (grey box). Hidden when insufficient data.
- REORDERED: delivery truck icon + "Delivery expected\n[date]" (blue box)

**When `status = "insufficient_data"`:**
- Historical dots/line only, no forecast segment
- Grey callout: "Run-out forecast unavailable\nWe need more consumption history before estimating when kibble will run out.\nStatus still uses your threshold setting.\nCheck back after a few more days."
- State badge still shows (STOCKED or REORDER_NOW based on level vs threshold)

**State badge (top-right of card header):**
Colored dot + label, pill-shaped background:

| State | Dot color | Label |
|---|---|---|
| STOCKED | Green | Stocked |
| REORDER_SOON | Orange | Reorder Soon |
| REORDER_NOW | Red | Reorder Now |
| REORDERED | Blue | On the way |

---

## Backend Changes

### Updated `ForecastResponse` schema

Three fields added to the existing response:

```python
class ReorderWindow(BaseModel):
    start: date
    end: date

class ActiveOrderInfo(BaseModel):
    product_name: str
    retailer_name: str
    estimated_delivery_date: date | None
    status: str  # "pending" | "placed" | "shipped"

class ForecastResponse(BaseModel):
    # ... existing fields unchanged ...
    forecast_state: str  # "stocked" | "reorder_soon" | "reorder_now" | "reordered"
    reorder_window: ReorderWindow | None  # None when insufficient_data
    active_order: ActiveOrderInfo | None  # None until Plan 6 places orders
```

### Forecast router changes (`app/routers/forecast.py`)

The `GET /bins/{bin_id}/forecast` handler gains:

1. **Active order lookup:** query `orders` table for the most recent order on this bin with status in `("pending", "placed", "shipped")`.
2. **Lead time lookup:** query `lead_times` for `(any retailer_id, user.pincode)`, take the minimum `estimated_days`. Fall back to city-tier baseline if no rows.
3. **State computation:** apply priority logic from the state model above.
4. **Reorder window:** `start = predicted_reorder_date`, `end = predicted_empty_date - avg_lead_time_days` (last safe day to place an order and still receive it before running out). Both dates come from the existing Prophet output combined with the lead time lookup.

### New service: `app/services/lead_time_service.py`

Single function:

```python
def get_avg_lead_time_days(pincode: str, lead_time_rows: list[LeadTime]) -> float:
    """Returns estimated lead time in days. Falls back to city-tier baseline."""
```

City-tier baseline uses a static dict mapping pincode prefixes to tier categories.

---

## Files Changed

**Backend:**
- `app/schemas/sensor.py` — add `ReorderWindow`, `ActiveOrderInfo`, extend `ForecastResponse`
- `app/routers/forecast.py` — active order lookup, lead time lookup, state computation
- `app/services/lead_time_service.py` — new file, lead time helper + city-tier baseline
- `tests/test_forecast.py` — tests for each of the 4 states + insufficient_data fallback

**Android:**
- `core/network/dto/ForecastDto.kt` — add `forecast_state`, `reorder_window`, `active_order` fields
- `feature/home/HomeState.kt` — add `ForecastState` enum, `reorderWindow`, `activeOrder`
- `feature/home/HomeViewModel.kt` — read `forecast_state` from response, map to `ForecastState`
- `feature/home/HomeScreen.kt` — state-driven subtitle, pass state color to container + chart
- `feature/home/components/KibbleContainer.kt` — accept `fillColor` from caller (already parameterized, just verify)
- `feature/home/components/ForecastChart.kt` — full redesign: filled area, dashed forecast, Today line, threshold line, callout box, state badge, insufficient_data callout
