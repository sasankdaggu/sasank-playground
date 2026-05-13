# Kibble Home Screen Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the home screen's status-word chart with a forecast-state-driven design: a `ForecastState` enum (STOCKED / REORDER_SOON / REORDER_NOW / REORDERED) computed on the backend drives container fill color, chart badge, subtitle text, and chart visual — giving users one clear signal instead of multiple confusing states.

**Architecture:** Backend computes `forecast_state`, `reorder_window`, and `active_order` and adds them to the existing `GET /bins/{bin_id}/forecast` response. Android reads the new fields and drives all visuals from `ForecastState`. The chart is rebuilt with filled areas, dashed forecast lines, today/threshold markers, and a callout box.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2 async / pytest-asyncio (backend); Kotlin 2 / Jetpack Compose / Hilt / kotlinx-serialization / JUnit 5 + MockK (Android).

---

## File Map

**Backend — new:**
- `backend/app/services/lead_time_service.py` — `get_avg_lead_time_days()` with city-tier baseline
- `backend/app/services/forecast_state.py` — `compute_forecast_state()` pure function
- `backend/tests/test_lead_time_service.py` — unit tests for lead time helper
- `backend/tests/test_forecast_state.py` — unit tests for state computation

**Backend — modified:**
- `backend/app/schemas/forecast.py` — add `ReorderWindow`, `ActiveOrderInfo`; extend `ForecastResponse`
- `backend/app/routers/forecast.py` — use new services; return new fields
- `backend/tests/test_forecast.py` — add HTTP endpoint tests for all 4 states

**Android — modified:**
- `android/core/network/src/main/kotlin/com/kibble/core/network/dto/ForecastDto.kt` — new DTOs
- `android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeState.kt` — `ForecastState` enum, simplified state
- `android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeViewModel.kt` — read backend state, compute subtitle
- `android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeScreen.kt` — state-driven colors, subtitle, badge
- `android/feature/home/src/main/kotlin/com/kibble/feature/home/components/KibbleContainer.kt` — remove `lowStock`/`warningColor`, use `fillColor` directly
- `android/feature/home/src/main/kotlin/com/kibble/feature/home/components/ForecastChart.kt` — full redesign

**Android — new:**
- `android/feature/home/src/test/kotlin/com/kibble/feature/home/HomeViewModelSubtitleTest.kt` — subtitle computation tests

---

### Task 1: Lead time service

**Files:**
- Create: `backend/app/services/lead_time_service.py`
- Create: `backend/tests/test_lead_time_service.py`

- [ ] **Step 1: Write the failing tests**

```bash
cat > /Users/sdagguba/kibble-reorder/backend/tests/test_lead_time_service.py << 'EOF'
import uuid
import pytest
from datetime import datetime, timezone
from app.models.lead_time import LeadTime
from app.services.lead_time_service import get_avg_lead_time_days

def make_lead_time(days: float) -> LeadTime:
    lt = LeadTime.__new__(LeadTime)
    lt.id = uuid.uuid4()
    lt.retailer_id = uuid.uuid4()
    lt.pincode = "110001"
    lt.estimated_days = days
    lt.source = "test"
    lt.recorded_at = datetime.now(timezone.utc)
    return lt

def test_metro_pincode_no_rows_returns_2():
    assert get_avg_lead_time_days("110001", []) == 2.0

def test_tier2_pincode_no_rows_returns_4():
    assert get_avg_lead_time_days("302001", []) == 4.0

def test_unknown_pincode_no_rows_returns_7():
    assert get_avg_lead_time_days("999999", []) == 7.0

def test_no_pincode_returns_7():
    assert get_avg_lead_time_days(None, []) == 7.0

def test_known_lead_time_overrides_tier():
    rows = [make_lead_time(1.5)]
    assert get_avg_lead_time_days("110001", rows) == 1.5

def test_multiple_lead_times_returns_minimum():
    rows = [make_lead_time(3.0), make_lead_time(1.5), make_lead_time(2.0)]
    assert get_avg_lead_time_days("110001", rows) == 1.5

def test_bangalore_pincode_is_metro():
    assert get_avg_lead_time_days("560001", []) == 2.0

def test_hyderabad_pincode_is_metro():
    assert get_avg_lead_time_days("500001", []) == 2.0
EOF
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest tests/test_lead_time_service.py -v 2>&1 | tail -15
```

Expected: `ImportError` or `ModuleNotFoundError` — `lead_time_service` doesn't exist yet.

- [ ] **Step 3: Implement lead_time_service.py**

```python
# backend/app/services/lead_time_service.py
from app.models.lead_time import LeadTime

_METRO_PREFIXES = {
    "110",        # Delhi
    "400", "401", # Mumbai
    "560",        # Bangalore
    "600",        # Chennai
    "700",        # Kolkata
    "500",        # Hyderabad
    "380",        # Ahmedabad
    "411",        # Pune
}

_TIER2_PREFIXES = {
    "302", "303", # Jaipur
    "160",        # Chandigarh
    "440",        # Nagpur
    "395",        # Surat
    "641",        # Coimbatore
    "530",        # Visakhapatnam
    "682",        # Kochi
    "226",        # Lucknow
    "800",        # Patna
    "781",        # Guwahati
    "248",        # Dehradun
    "462",        # Bhopal
    "492",        # Raipur
    "751",        # Bhubaneswar
    "390",        # Vadodara
}

def get_avg_lead_time_days(pincode: str | None, lead_time_rows: list[LeadTime]) -> float:
    """Returns min known lead time in days, or city-tier baseline if no data."""
    if lead_time_rows:
        return min(r.estimated_days for r in lead_time_rows)
    if pincode and len(pincode) >= 3:
        prefix = pincode[:3]
        if prefix in _METRO_PREFIXES:
            return 2.0
        if prefix in _TIER2_PREFIXES:
            return 4.0
    return 7.0
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest tests/test_lead_time_service.py -v 2>&1 | tail -15
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add backend/app/services/lead_time_service.py backend/tests/test_lead_time_service.py && git commit -m "feat(backend): lead_time_service — city-tier baseline for pincode-based lead times"
```

---

### Task 2: Forecast state service

**Files:**
- Create: `backend/app/services/forecast_state.py`
- Create: `backend/tests/test_forecast_state.py`

- [ ] **Step 1: Write the failing tests**

```bash
cat > /Users/sdagguba/kibble-reorder/backend/tests/test_forecast_state.py << 'EOF'
from datetime import datetime, timedelta, timezone
import pytest
from app.services.forecast_state import compute_forecast_state

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

def test_reordered_takes_priority_over_low_level():
    state = compute_forecast_state(
        level_pct=10.0, reorder_threshold_pct=20,
        predicted_reorder_date=None, lead_time_days=3.0,
        has_active_order=True, now=NOW,
    )
    assert state == "reordered"

def test_reorder_now_when_level_at_threshold():
    state = compute_forecast_state(
        level_pct=20.0, reorder_threshold_pct=20,
        predicted_reorder_date=None, lead_time_days=3.0,
        has_active_order=False, now=NOW,
    )
    assert state == "reorder_now"

def test_reorder_now_when_level_below_threshold():
    state = compute_forecast_state(
        level_pct=15.0, reorder_threshold_pct=20,
        predicted_reorder_date=None, lead_time_days=3.0,
        has_active_order=False, now=NOW,
    )
    assert state == "reorder_now"

def test_reorder_soon_when_reorder_date_within_lead_time_plus_buffer():
    # reorder date is 3 days away, lead_time is 3 → deadline = now+4, so 3 < 4 → reorder_soon
    pred_date = NOW + timedelta(days=3)
    state = compute_forecast_state(
        level_pct=50.0, reorder_threshold_pct=20,
        predicted_reorder_date=pred_date, lead_time_days=3.0,
        has_active_order=False, now=NOW,
    )
    assert state == "reorder_soon"

def test_stocked_when_reorder_date_far_away():
    pred_date = NOW + timedelta(days=30)
    state = compute_forecast_state(
        level_pct=80.0, reorder_threshold_pct=20,
        predicted_reorder_date=pred_date, lead_time_days=3.0,
        has_active_order=False, now=NOW,
    )
    assert state == "stocked"

def test_stocked_when_no_predicted_date_and_level_above_threshold():
    state = compute_forecast_state(
        level_pct=80.0, reorder_threshold_pct=20,
        predicted_reorder_date=None, lead_time_days=3.0,
        has_active_order=False, now=NOW,
    )
    assert state == "stocked"

def test_stocked_when_level_pct_is_none():
    state = compute_forecast_state(
        level_pct=None, reorder_threshold_pct=20,
        predicted_reorder_date=None, lead_time_days=3.0,
        has_active_order=False, now=NOW,
    )
    assert state == "stocked"
EOF
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest tests/test_forecast_state.py -v 2>&1 | tail -15
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Implement forecast_state.py**

```python
# backend/app/services/forecast_state.py
from datetime import datetime, timedelta, timezone

def compute_forecast_state(
    level_pct: float | None,
    reorder_threshold_pct: int,
    predicted_reorder_date: datetime | None,
    lead_time_days: float,
    has_active_order: bool,
    now: datetime | None = None,
) -> str:
    """Returns one of: 'reordered', 'reorder_now', 'reorder_soon', 'stocked'."""
    if now is None:
        now = datetime.now(timezone.utc)
    if has_active_order:
        return "reordered"
    if level_pct is not None and level_pct <= reorder_threshold_pct:
        return "reorder_now"
    if predicted_reorder_date is not None:
        deadline = now + timedelta(days=lead_time_days + 1)
        if predicted_reorder_date <= deadline:
            return "reorder_soon"
    return "stocked"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest tests/test_forecast_state.py -v 2>&1 | tail -15
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add backend/app/services/forecast_state.py backend/tests/test_forecast_state.py && git commit -m "feat(backend): forecast_state service — compute STOCKED/REORDER_SOON/REORDER_NOW/REORDERED"
```

---

### Task 3: Extend forecast schema

**Files:**
- Modify: `backend/app/schemas/forecast.py`

- [ ] **Step 1: Replace the file contents**

```python
# backend/app/schemas/forecast.py
from datetime import datetime, date
from pydantic import BaseModel


class ForecastPoint(BaseModel):
    timestamp: datetime
    level_pct: float
    level_pct_lower: float
    level_pct_upper: float
    is_historical: bool


class ReorderWindow(BaseModel):
    start: datetime
    end: datetime


class ActiveOrderInfo(BaseModel):
    product_name: str
    retailer_name: str
    estimated_delivery_date: date | None
    status: str  # "pending" | "placed" | "shipped"


class ForecastResponse(BaseModel):
    status: str  # "ok" | "insufficient_data"
    reorder_threshold_pct: int
    predicted_reorder_date: datetime | None
    predicted_empty_date: datetime | None
    forecast: list[ForecastPoint]
    forecast_state: str = "stocked"  # "stocked"|"reorder_soon"|"reorder_now"|"reordered"
    reorder_window: ReorderWindow | None = None
    active_order: ActiveOrderInfo | None = None
```

- [ ] **Step 2: Run all backend tests to confirm existing tests still pass**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest -q 2>&1 | tail -5
```

Expected: all 58+ tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add backend/app/schemas/forecast.py && git commit -m "feat(backend): extend ForecastResponse with forecast_state, reorder_window, active_order"
```

---

### Task 4: Update forecast router

**Files:**
- Modify: `backend/app/routers/forecast.py`

- [ ] **Step 1: Replace the router with the updated version**

```python
# backend/app/routers/forecast.py
import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.database import get_db
from app.auth.deps import get_current_user
from app.models.bin import Bin
from app.models.lead_time import LeadTime
from app.models.order import Order
from app.models.retailer import Retailer
from app.models.sensor_reading import SensorReading
from app.models.user import User
from app.schemas.forecast import (
    ActiveOrderInfo,
    ForecastPoint,
    ForecastResponse,
    ReorderWindow,
)
from app.services.forecast_state import compute_forecast_state
from app.services.lead_time_service import get_avg_lead_time_days
from app.services.prophet_forecast import build_prophet_forecast

router = APIRouter()


@router.get("/bins/{bin_id}/forecast", response_model=ForecastResponse)
async def get_forecast(
    bin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bin_ = await db.get(Bin, bin_id)
    if not bin_:
        raise HTTPException(status_code=404, detail="Bin not found")
    if bin_.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # --- active order ---
    active_order_row = await db.scalar(
        select(Order)
        .where(Order.bin_id == bin_id, Order.status.in_(["pending", "placed", "shipped"]))
        .order_by(Order.placed_at.desc())
        .limit(1)
    )
    active_order_info: ActiveOrderInfo | None = None
    if active_order_row:
        retailer = await db.get(Retailer, active_order_row.retailer_id)
        active_order_info = ActiveOrderInfo(
            product_name=active_order_row.product_name,
            retailer_name=retailer.name if retailer else "Unknown",
            estimated_delivery_date=active_order_row.estimated_delivery_date,
            status=active_order_row.status,
        )

    # --- lead time ---
    lead_time_rows = list(await db.scalars(
        select(LeadTime).where(LeadTime.pincode == current_user.pincode)
    ))
    lead_time_days = get_avg_lead_time_days(current_user.pincode, lead_time_rows)

    # --- insufficient data (not calibrated) ---
    if bin_.calibration_state != "fully_calibrated":
        latest_reading = await db.scalar(
            select(SensorReading)
            .where(SensorReading.bin_id == bin_id, SensorReading.kibble_level_pct.is_not(None))
            .order_by(SensorReading.timestamp.desc())
            .limit(1)
        )
        level_pct = latest_reading.kibble_level_pct if latest_reading else None
        state = compute_forecast_state(
            level_pct=level_pct,
            reorder_threshold_pct=current_user.reorder_threshold_pct,
            predicted_reorder_date=None,
            lead_time_days=lead_time_days,
            has_active_order=active_order_row is not None,
        )
        return ForecastResponse(
            status="insufficient_data",
            reorder_threshold_pct=current_user.reorder_threshold_pct,
            predicted_reorder_date=None,
            predicted_empty_date=None,
            forecast=[],
            forecast_state=state,
            reorder_window=None,
            active_order=active_order_info,
        )

    # --- readings ---
    readings_rows = await db.scalars(
        select(SensorReading)
        .where(
            SensorReading.bin_id == bin_id,
            SensorReading.kibble_level_pct.is_not(None),
            SensorReading.is_refill_event.is_(False),
        )
        .order_by(SensorReading.timestamp.asc())
    )
    readings = [(r.timestamp, r.kibble_level_pct) for r in readings_rows.all()]

    result = await run_in_threadpool(
        build_prophet_forecast, readings, current_user.reorder_threshold_pct
    )

    # --- state + window (insufficient_data from Prophet: < 4 readings) ---
    if result.status == "insufficient_data":
        latest_reading = await db.scalar(
            select(SensorReading)
            .where(SensorReading.bin_id == bin_id, SensorReading.kibble_level_pct.is_not(None))
            .order_by(SensorReading.timestamp.desc())
            .limit(1)
        )
        level_pct = latest_reading.kibble_level_pct if latest_reading else None
        state = compute_forecast_state(
            level_pct=level_pct,
            reorder_threshold_pct=current_user.reorder_threshold_pct,
            predicted_reorder_date=None,
            lead_time_days=lead_time_days,
            has_active_order=active_order_row is not None,
        )
        return ForecastResponse(
            status="insufficient_data",
            reorder_threshold_pct=current_user.reorder_threshold_pct,
            predicted_reorder_date=None,
            predicted_empty_date=None,
            forecast=[],
            forecast_state=state,
            reorder_window=None,
            active_order=active_order_info,
        )

    # --- full forecast ---
    historical_points = [p for p in result.forecast if p.is_historical]
    latest_level_pct = historical_points[-1].level_pct if historical_points else None

    state = compute_forecast_state(
        level_pct=latest_level_pct,
        reorder_threshold_pct=current_user.reorder_threshold_pct,
        predicted_reorder_date=result.predicted_reorder_date,
        lead_time_days=lead_time_days,
        has_active_order=active_order_row is not None,
    )

    reorder_window: ReorderWindow | None = None
    if result.predicted_reorder_date and result.predicted_empty_date:
        window_end = result.predicted_empty_date - timedelta(days=lead_time_days)
        if window_end > result.predicted_reorder_date:
            reorder_window = ReorderWindow(
                start=result.predicted_reorder_date,
                end=window_end,
            )

    return ForecastResponse(
        status=result.status,
        reorder_threshold_pct=result.reorder_threshold_pct,
        predicted_reorder_date=result.predicted_reorder_date,
        predicted_empty_date=result.predicted_empty_date,
        forecast=[
            ForecastPoint(
                timestamp=p.timestamp,
                level_pct=p.level_pct,
                level_pct_lower=p.level_pct_lower,
                level_pct_upper=p.level_pct_upper,
                is_historical=p.is_historical,
            )
            for p in result.forecast
        ],
        forecast_state=state,
        reorder_window=reorder_window,
        active_order=active_order_info,
    )
```

- [ ] **Step 2: Run all backend tests**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add backend/app/routers/forecast.py && git commit -m "feat(backend): forecast router returns forecast_state, reorder_window, active_order"
```

---

### Task 5: Forecast HTTP endpoint integration tests

**Files:**
- Modify: `backend/tests/test_forecast.py`

- [ ] **Step 1: Add the new tests at the bottom of the existing file**

Read the current end of the file first:
```bash
tail -5 /Users/sdagguba/kibble-reorder/backend/tests/test_forecast.py
```

Then append these tests. The `user_bin` fixture (from `conftest.py`) returns `(user, bin_, headers)` and creates a user with `pincode=None` and `reorder_threshold_pct=20`.

```python
# --- append to backend/tests/test_forecast.py ---

import pytest
from datetime import datetime, date, timezone, timedelta
import uuid
from httpx import AsyncClient


async def _calibrate_bin(client: AsyncClient, bin_id: str, headers: dict) -> None:
    """Set bin to fully_calibrated with empty=600mm, full=50mm."""
    await client.post(f"/bins/{bin_id}/calibrate/empty",
                      json={"distance_mm": 600.0}, headers=headers)
    await client.post(f"/bins/{bin_id}/calibrate/full",
                      json={"distance_mm": 50.0}, headers=headers)


async def _post_reading(client: AsyncClient, bin_id: str, headers: dict,
                        distance_mm: float) -> None:
    await client.post(f"/bins/{bin_id}/readings",
                      json={"distance_mm": distance_mm}, headers=headers)


@pytest.mark.asyncio
async def test_forecast_state_stocked_insufficient_data(user_bin, client):
    user, bin_, headers = user_bin
    await _calibrate_bin(client, bin_["id"], headers)
    # 2 readings (< 4) with level well above threshold
    await _post_reading(client, bin_["id"], headers, 200.0)  # ~73% full
    await _post_reading(client, bin_["id"], headers, 210.0)  # ~71% full
    resp = await client.get(f"/bins/{bin_['id']}/forecast", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "insufficient_data"
    assert body["forecast_state"] == "stocked"
    assert body["reorder_window"] is None


@pytest.mark.asyncio
async def test_forecast_state_reorder_now_insufficient_data(user_bin, client):
    user, bin_, headers = user_bin
    await _calibrate_bin(client, bin_["id"], headers)
    # level below threshold (threshold=20, level ~3%)
    await _post_reading(client, bin_["id"], headers, 580.0)
    await _post_reading(client, bin_["id"], headers, 582.0)
    resp = await client.get(f"/bins/{bin_['id']}/forecast", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "insufficient_data"
    assert body["forecast_state"] == "reorder_now"


@pytest.mark.asyncio
async def test_forecast_state_reordered_with_active_order(user_bin, client):
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.config import settings
    from app.models.retailer import Retailer
    from app.models.order import Order
    from app.models.user import User as UserModel
    from sqlalchemy import select

    user, bin_, headers = user_bin
    await _calibrate_bin(client, bin_["id"], headers)
    await _post_reading(client, bin_["id"], headers, 580.0)
    await _post_reading(client, bin_["id"], headers, 582.0)

    engine = create_async_engine(settings.database_url_test)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        retailer = Retailer(id=uuid.uuid4(), name="Supertails",
                            base_url="https://supertails.com",
                            plugin_class="SupertailsPlugin", retailer_type="standard")
        session.add(retailer)
        user_row = await session.scalar(select(UserModel).where(UserModel.id == uuid.UUID(user["user_id"])))
        order = Order(
            id=uuid.uuid4(), user_id=user_row.id,
            bin_id=uuid.UUID(bin_["id"]), retailer_id=retailer.id,
            product_name="Royal Canin 10kg", pack_size_kg=10.0,
            total_price=2500.0, shipping_cost=0.0, price_per_kg=250.0,
            status="placed",
        )
        session.add(order)
        await session.commit()
    await engine.dispose()

    resp = await client.get(f"/bins/{bin_['id']}/forecast", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["forecast_state"] == "reordered"
    assert body["active_order"]["retailer_name"] == "Supertails"
    assert body["active_order"]["status"] == "placed"


@pytest.mark.asyncio
async def test_forecast_state_stocked_full_forecast(user_bin, client):
    """7 days of readings well above threshold → status=ok, forecast_state=stocked."""
    from datetime import datetime, timedelta
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.config import settings
    from app.models.sensor_reading import SensorReading
    from app.models.bin import Bin
    from sqlalchemy import select

    user, bin_, headers = user_bin
    await _calibrate_bin(client, bin_["id"], headers)

    engine = create_async_engine(settings.database_url_test)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        bin_row = await session.get(Bin, uuid.UUID(bin_["id"]))
        # 28 readings over 7 days, level from 80% down to 45% (well above 20% threshold)
        for i in range(28):
            dist = 50 + (600 - 50) * (1 - (0.80 - i * 0.0125))  # level 80%→45%
            ts = datetime.now(timezone.utc) - timedelta(hours=(27 - i) * 6)
            reading = SensorReading(
                id=uuid.uuid4(), bin_id=bin_row.id,
                timestamp=ts, distance_mm=dist,
                kibble_level_pct=80.0 - i * 1.25,
                kibble_kg_remaining=0.0, is_refill_event=False,
            )
            session.add(reading)
        await session.commit()
    await engine.dispose()

    resp = await client.get(f"/bins/{bin_['id']}/forecast", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["forecast_state"] == "stocked"
    assert body["reorder_window"] is not None
    assert body["active_order"] is None


@pytest.mark.asyncio
async def test_forecast_response_has_new_fields(user_bin, client):
    user, bin_, headers = user_bin
    resp = await client.get(f"/bins/{bin_['id']}/forecast", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "forecast_state" in body
    assert "reorder_window" in body
    assert "active_order" in body
```

- [ ] **Step 2: Run the new tests**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest tests/test_forecast.py -v 2>&1 | tail -20
```

Expected: all tests in the file pass (existing 4 + new 5).

- [ ] **Step 3: Run full suite**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add backend/tests/test_forecast.py && git commit -m "test(backend): forecast HTTP endpoint — all 4 forecast states + new response fields"
```

---

### Task 6: Android ForecastDto extensions

**Files:**
- Modify: `android/core/network/src/main/kotlin/com/kibble/core/network/dto/ForecastDto.kt`

- [ ] **Step 1: Replace the file contents**

```kotlin
// android/core/network/src/main/kotlin/com/kibble/core/network/dto/ForecastDto.kt
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class ForecastPoint(
    val timestamp: String,
    val level_pct: Double,
    val level_pct_lower: Double? = null,
    val level_pct_upper: Double? = null,
    val is_historical: Boolean,
)

@Serializable
data class ReorderWindow(
    val start: String,
    val end: String,
)

@Serializable
data class ActiveOrderInfo(
    val product_name: String,
    val retailer_name: String,
    val estimated_delivery_date: String? = null,
    val status: String,
)

@Serializable
data class ForecastResponse(
    val status: String,
    val reorder_threshold_pct: Int,
    val predicted_reorder_date: String? = null,
    val predicted_empty_date: String? = null,
    val forecast: List<ForecastPoint> = emptyList(),
    val forecast_state: String = "stocked",
    val reorder_window: ReorderWindow? = null,
    val active_order: ActiveOrderInfo? = null,
)
```

- [ ] **Step 2: Build to confirm it compiles**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :core:network:compileDebugKotlin 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add android/core/network/src/main/kotlin/com/kibble/core/network/dto/ForecastDto.kt && git commit -m "feat(android): ForecastDto — add ReorderWindow, ActiveOrderInfo, extend ForecastResponse"
```

---

### Task 7: HomeState + HomeViewModel

**Files:**
- Modify: `android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeState.kt`
- Modify: `android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeViewModel.kt`
- Create: `android/feature/home/src/test/kotlin/com/kibble/feature/home/HomeViewModelSubtitleTest.kt`

- [ ] **Step 1: Write the subtitle tests first**

Create the test directory if it doesn't exist:
```bash
mkdir -p /Users/sdagguba/kibble-reorder/android/feature/home/src/test/kotlin/com/kibble/feature/home
```

```kotlin
// android/feature/home/src/test/kotlin/com/kibble/feature/home/HomeViewModelSubtitleTest.kt
package com.kibble.feature.home

import com.kibble.core.network.dto.ActiveOrderInfo
import com.kibble.core.network.dto.ForecastResponse
import com.kibble.core.network.dto.ReorderWindow
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class HomeViewModelSubtitleTest {

    private fun subtitle(
        state: ForecastState,
        dogName: String? = "Max",
        forecast: ForecastResponse? = null,
    ) = buildSubtitle(state, dogName, forecast)

    @Test fun stocked_with_empty_date_shows_dog_name_and_date() {
        val forecast = ForecastResponse(
            status = "ok", reorder_threshold_pct = 20,
            predicted_empty_date = "2026-05-18T00:00:00Z",
            forecast_state = "stocked",
        )
        val s = subtitle(ForecastState.STOCKED, "Buddy", forecast)
        assertTrue(s.contains("Buddy"))
        assertTrue(s.contains("May 18"))
    }

    @Test fun stocked_no_dog_name_falls_back() {
        val forecast = ForecastResponse(
            status = "ok", reorder_threshold_pct = 20,
            predicted_empty_date = "2026-05-18T00:00:00Z",
            forecast_state = "stocked",
        )
        val s = subtitle(ForecastState.STOCKED, null, forecast)
        assertTrue(s.contains("food lasts until"))
    }

    @Test fun stocked_insufficient_data_shows_building_message() {
        val forecast = ForecastResponse(
            status = "insufficient_data", reorder_threshold_pct = 20,
            forecast_state = "stocked",
        )
        val s = subtitle(ForecastState.STOCKED, "Max", forecast)
        assertTrue(s.contains("forecast building"))
    }

    @Test fun stocked_no_forecast_shows_connect_sensor() {
        val s = subtitle(ForecastState.STOCKED, "Max", null)
        assertTrue(s.contains("Connect sensor"))
    }

    @Test fun reorder_soon_shows_order_by_date() {
        val forecast = ForecastResponse(
            status = "ok", reorder_threshold_pct = 20,
            reorder_window = ReorderWindow("2026-05-02T00:00:00Z", "2026-05-06T00:00:00Z"),
            forecast_state = "reorder_soon",
        )
        val s = subtitle(ForecastState.REORDER_SOON, "Max", forecast)
        assertTrue(s.contains("May 2"))
        assertTrue(s.contains("running out"))
    }

    @Test fun reorder_now_shows_running_low() {
        val s = subtitle(ForecastState.REORDER_NOW, "Max", null)
        assertEquals("Running low — reorder now", s)
    }

    @Test fun reordered_with_delivery_date_shows_date() {
        val forecast = ForecastResponse(
            status = "ok", reorder_threshold_pct = 20,
            active_order = ActiveOrderInfo("Royal Canin 10kg", "Supertails", "2026-05-03", "placed"),
            forecast_state = "reordered",
        )
        val s = subtitle(ForecastState.REORDERED, "Max", forecast)
        assertTrue(s.contains("May 3"))
    }

    @Test fun reordered_without_delivery_date_shows_on_the_way() {
        val forecast = ForecastResponse(
            status = "ok", reorder_threshold_pct = 20,
            active_order = ActiveOrderInfo("Royal Canin 10kg", "Supertails", null, "placed"),
            forecast_state = "reordered",
        )
        val s = subtitle(ForecastState.REORDERED, "Max", forecast)
        assertTrue(s.contains("on its way"))
    }
}
```

- [ ] **Step 2: Run the failing tests**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:home:test 2>&1 | tail -15
```

Expected: compile error — `ForecastState`, `buildSubtitle` don't exist yet.

- [ ] **Step 3: Update HomeState.kt**

```kotlin
// android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeState.kt
package com.kibble.feature.home

import com.kibble.core.database.entity.SensorReadingEntity
import com.kibble.core.network.dto.ForecastResponse

enum class ForecastState { STOCKED, REORDER_SOON, REORDER_NOW, REORDERED }

data class HomeState(
    val isLoading: Boolean = true,
    val dogName: String? = null,
    val levelPct: Double? = null,
    val forecast: ForecastResponse? = null,
    val latestReading: SensorReadingEntity? = null,
    val forecastState: ForecastState = ForecastState.STOCKED,
    val subtitle: String = "",
    val error: String? = null,
)

sealed class HomeIntent {
    data object OnTapReadNow : HomeIntent()
    data object OnRefresh : HomeIntent()
}
```

- [ ] **Step 4: Update HomeViewModel.kt**

```kotlin
// android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeViewModel.kt
package com.kibble.feature.home

import android.content.Context
import android.content.Intent
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.DogDao
import com.kibble.core.database.dao.SensorReadingDao
import com.kibble.core.database.dao.UserDao
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.ForecastResponse
import com.kibble.service.ble.BleForegroundService
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import javax.inject.Inject

private val DATE_FMT = DateTimeFormatter.ofPattern("MMM d").withZone(ZoneId.systemDefault())

internal fun buildSubtitle(
    state: ForecastState,
    dogName: String?,
    forecast: ForecastResponse?,
): String {
    val name = dogName ?: "your dog"
    return when (state) {
        ForecastState.REORDERED -> {
            val deliveryDate = forecast?.active_order?.estimated_delivery_date
            if (deliveryDate != null) {
                val formatted = runCatching {
                    DATE_FMT.format(Instant.parse("${deliveryDate}T00:00:00Z"))
                }.getOrElse { deliveryDate }
                "Order arriving $formatted"
            } else {
                "Order on its way"
            }
        }
        ForecastState.REORDER_NOW -> "Running low — reorder now"
        ForecastState.REORDER_SOON -> {
            val windowStart = forecast?.reorder_window?.start
            if (windowStart != null) {
                val formatted = runCatching {
                    DATE_FMT.format(Instant.parse(windowStart))
                }.getOrElse { windowStart }
                "Order by $formatted to avoid running out"
            } else {
                "Order soon to avoid running out"
            }
        }
        ForecastState.STOCKED -> when {
            forecast == null -> "Connect sensor to get started"
            forecast.status == "insufficient_data" -> "Plenty of food · forecast building"
            forecast.predicted_empty_date != null -> {
                val formatted = runCatching {
                    DATE_FMT.format(Instant.parse(forecast.predicted_empty_date))
                }.getOrElse { forecast.predicted_empty_date }
                "$name's food lasts until $formatted"
            }
            else -> "Plenty of food"
        }
    }
}

private fun mapForecastState(raw: String): ForecastState = when (raw) {
    "reorder_soon" -> ForecastState.REORDER_SOON
    "reorder_now" -> ForecastState.REORDER_NOW
    "reordered" -> ForecastState.REORDERED
    else -> ForecastState.STOCKED
}

@HiltViewModel
class HomeViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val userDao: UserDao,
    private val dogDao: DogDao,
    private val binDao: BinDao,
    private val sensorDao: SensorReadingDao,
    private val api: KibbleApi,
) : ViewModel() {

    private val _state = MutableStateFlow(HomeState())
    val state = _state.asStateFlow()

    init { viewModelScope.launch { observe() } }

    private suspend fun observe() {
        val user = userDao.first() ?: run { _state.value = _state.value.copy(isLoading = false); return }
        val bin = binDao.observeForUser(user.id).firstOrNull()?.firstOrNull() ?: run {
            _state.value = _state.value.copy(isLoading = false); return
        }
        val dogName = dogDao.observeForUser(user.id).firstOrNull()?.firstOrNull()?.name
        sensorDao.observeLatest(bin.id).collect { latest ->
            val forecast = runCatching { api.getForecast(bin.id.toString()) }.getOrNull()
            val historical = forecast?.forecast?.filter { it.is_historical } ?: emptyList()
            val latestLevel = historical.lastOrNull()?.level_pct
            val forecastState = mapForecastState(forecast?.forecast_state ?: "stocked")
            _state.value = _state.value.copy(
                isLoading = false,
                dogName = dogName,
                latestReading = latest,
                forecast = forecast,
                levelPct = latestLevel,
                forecastState = forecastState,
                subtitle = buildSubtitle(forecastState, dogName, forecast),
            )
        }
    }

    fun handle(intent: HomeIntent) {
        when (intent) {
            HomeIntent.OnTapReadNow -> context.startForegroundService(
                Intent(context, BleForegroundService::class.java).apply {
                    action = BleForegroundService.ACTION_READ_NOW
                }
            )
            HomeIntent.OnRefresh -> viewModelScope.launch { observe() }
        }
    }
}
```

- [ ] **Step 5: Run the tests**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:home:test 2>&1 | tail -15
```

Expected: 8 tests pass.

- [ ] **Step 6: Full build check**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :app:assembleDebug 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeState.kt android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeViewModel.kt android/feature/home/src/test/kotlin/com/kibble/feature/home/HomeViewModelSubtitleTest.kt && git commit -m "feat(android): ForecastState enum + subtitle computation in HomeViewModel"
```

---

### Task 8: HomeScreen + KibbleContainer — state-driven colors and badge

**Files:**
- Modify: `android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeScreen.kt`
- Modify: `android/feature/home/src/main/kotlin/com/kibble/feature/home/components/KibbleContainer.kt`

- [ ] **Step 1: Update KibbleContainer — remove lowStock/warningColor, use fillColor directly**

```kotlin
// android/feature/home/src/main/kotlin/com/kibble/feature/home/components/KibbleContainer.kt
package com.kibble.feature.home.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.unit.dp

@Composable
fun KibbleContainer(
    levelPct: Double,
    fillColor: Color,
    containerBorderColor: Color,
    containerBackgroundColor: Color,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier.size(width = 200.dp, height = 240.dp)) {
        val w = size.width
        val h = size.height
        val bodyTop = h * 0.30f
        val bodyBottom = h * 0.94f
        val bodyLeft = w * 0.20f
        val bodyRight = w * 0.80f
        val cornerR = 24f

        val bodyPath = Path().apply {
            moveTo(bodyLeft, bodyTop + cornerR)
            quadraticBezierTo(bodyLeft, bodyTop, bodyLeft + cornerR, bodyTop)
            lineTo(bodyRight - cornerR, bodyTop)
            quadraticBezierTo(bodyRight, bodyTop, bodyRight, bodyTop + cornerR)
            lineTo(bodyRight, bodyBottom - cornerR)
            quadraticBezierTo(bodyRight, bodyBottom, bodyRight - cornerR, bodyBottom)
            lineTo(bodyLeft + cornerR, bodyBottom)
            quadraticBezierTo(bodyLeft, bodyBottom, bodyLeft, bodyBottom - cornerR)
            close()
        }

        drawPath(bodyPath, color = containerBackgroundColor)
        drawPath(bodyPath, color = containerBorderColor, style = Stroke(width = 4f))

        clipPath(bodyPath) {
            val fillTop = bodyBottom - (bodyBottom - bodyTop) * (levelPct.toFloat() / 100f).coerceIn(0f, 1f)
            drawRect(
                color = fillColor,
                topLeft = Offset(bodyLeft, fillTop),
                size = Size(bodyRight - bodyLeft, bodyBottom - fillTop),
            )
        }

        drawRoundRect(
            color = containerBorderColor,
            topLeft = Offset(bodyLeft - 8f, bodyTop - 28f),
            size = Size((bodyRight - bodyLeft) + 16f, 28f),
            cornerRadius = CornerRadius(8f),
        )

        drawOval(
            color = Color(0xFF98D2BF),
            topLeft = Offset(w / 2 - 16f, bodyTop - 36f),
            size = Size(32f, 14f),
        )
    }
}
```

- [ ] **Step 2: Update HomeScreen.kt**

```kotlin
// android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeScreen.kt
package com.kibble.feature.home

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kibble.feature.home.components.ForecastChart
import com.kibble.feature.home.components.KibbleContainer

private val ColorStocked = Color(0xFF155243)
private val ColorReorderSoon = Color(0xFFE07B39)
private val ColorReorderNow = Color(0xFFC0392B)
private val ColorReordered = Color(0xFF2C6FA6)

private fun stateColor(state: ForecastState): Color = when (state) {
    ForecastState.STOCKED -> ColorStocked
    ForecastState.REORDER_SOON -> ColorReorderSoon
    ForecastState.REORDER_NOW -> ColorReorderNow
    ForecastState.REORDERED -> ColorReordered
}

private fun stateBadgeLabel(state: ForecastState): String = when (state) {
    ForecastState.STOCKED -> "Stocked"
    ForecastState.REORDER_SOON -> "Reorder Soon"
    ForecastState.REORDER_NOW -> "Reorder Now"
    ForecastState.REORDERED -> "On the way"
}

private fun blePermissionsGranted(context: android.content.Context): Boolean {
    val perms = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    } else {
        arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    return perms.all { ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(viewModel: HomeViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val color = stateColor(state.forecastState)

    val blePerms = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    } else {
        arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results -> if (results.values.all { it }) viewModel.handle(HomeIntent.OnTapReadNow) }

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Text("Kibble", style = MaterialTheme.typography.titleLarge.copy(fontStyle = FontStyle.Italic))
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = color,
                    titleContentColor = Color.White,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(padding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            KibbleContainer(
                levelPct = state.levelPct ?: 0.0,
                fillColor = color,
                containerBorderColor = color,
                containerBackgroundColor = color.copy(alpha = 0.12f),
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "${state.levelPct?.toInt() ?: "--"}%",
                style = MaterialTheme.typography.displayLarge,
                color = color,
            )
            Text(
                state.subtitle,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
            )
            Spacer(Modifier.height(24.dp))

            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    // Card header: title + state badge
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            "KIBBLE INVENTORY FORECAST",
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.weight(1f),
                        )
                        // State badge pill
                        Surface(
                            color = color.copy(alpha = 0.15f),
                            shape = RoundedCornerShape(50),
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(5.dp),
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(8.dp)
                                        .background(color, CircleShape)
                                )
                                Text(
                                    stateBadgeLabel(state.forecastState),
                                    style = MaterialTheme.typography.labelMedium,
                                    color = color,
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                    ForecastChart(
                        historical = state.forecast?.forecast?.filter { it.is_historical } ?: emptyList(),
                        forecast = state.forecast?.forecast?.filter { !it.is_historical } ?: emptyList(),
                        status = state.forecast?.status ?: "insufficient_data",
                        forecastState = state.forecastState,
                        stateColor = color,
                        reorderThresholdPct = state.forecast?.reorder_threshold_pct ?: 20,
                        reorderWindow = state.forecast?.reorder_window,
                        activeOrder = state.forecast?.active_order,
                    )
                }
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    if (blePermissionsGranted(context)) viewModel.handle(HomeIntent.OnTapReadNow)
                    else permissionLauncher.launch(blePerms)
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = color),
            ) { Text("READ NOW") }
        }
    }
}
```

- [ ] **Step 3: Build to confirm it compiles**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:home:compileDebugKotlin 2>&1 | tail -8
```

Expected: `BUILD SUCCESSFUL` (there will be a compile error about `ForecastChart` signature mismatch — fix in Task 9).

If ForecastChart signature errors appear, temporarily add default values to the new params in ForecastChart.kt to unblock compilation, then replace the whole file in Task 9.

- [ ] **Step 4: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add android/feature/home/src/main/kotlin/com/kibble/feature/home/HomeScreen.kt android/feature/home/src/main/kotlin/com/kibble/feature/home/components/KibbleContainer.kt && git commit -m "feat(android): HomeScreen + KibbleContainer — forecast-state-driven colors and badge"
```

---

### Task 9: ForecastChart redesign

**Files:**
- Modify: `android/feature/home/src/main/kotlin/com/kibble/feature/home/components/ForecastChart.kt`

- [ ] **Step 1: Replace ForecastChart.kt with the full redesign**

```kotlin
// android/feature/home/src/main/kotlin/com/kibble/feature/home/components/ForecastChart.kt
package com.kibble.feature.home.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.Canvas
import com.kibble.core.network.dto.ActiveOrderInfo
import com.kibble.core.network.dto.ForecastPoint
import com.kibble.core.network.dto.ReorderWindow
import com.kibble.feature.home.ForecastState
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val DATE_SHORT = DateTimeFormatter.ofPattern("MMM d").withZone(ZoneId.systemDefault())

private fun fmtDate(iso: String?): String {
    if (iso == null) return "—"
    return runCatching { DATE_SHORT.format(Instant.parse(iso)) }.getOrElse { "—" }
}

@Composable
fun ForecastChart(
    historical: List<ForecastPoint>,
    forecast: List<ForecastPoint>,
    status: String,
    forecastState: ForecastState,
    stateColor: Color,
    reorderThresholdPct: Int,
    reorderWindow: ReorderWindow?,
    activeOrder: ActiveOrderInfo?,
    modifier: Modifier = Modifier,
) {
    val all = historical + forecast
    val hasData = all.isNotEmpty()

    // Callout box content
    val calloutContent: (@Composable () -> Unit)? = when {
        forecastState == ForecastState.REORDERED && activeOrder != null -> ({
            Column(modifier = Modifier.padding(8.dp)) {
                Text("🚚", style = MaterialTheme.typography.bodyMedium)
                Text("Delivery expected", style = MaterialTheme.typography.labelSmall,
                    color = stateColor)
                Text(fmtDate(activeOrder.estimated_delivery_date),
                    style = MaterialTheme.typography.bodySmall)
            }
        })
        status == "insufficient_data" -> ({
            Column(modifier = Modifier.padding(8.dp)) {
                Text("Run-out forecast unavailable",
                    style = MaterialTheme.typography.labelSmall)
                Text("Check back after a few more days.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }
        })
        reorderWindow != null -> ({
            Column(modifier = Modifier.padding(8.dp)) {
                Text("Recommended reorder window",
                    style = MaterialTheme.typography.labelSmall)
                Text("${fmtDate(reorderWindow.start)} – ${fmtDate(reorderWindow.end)}",
                    style = MaterialTheme.typography.bodySmall)
            }
        })
        else -> null
    }

    Column(modifier = modifier.fillMaxWidth()) {
        Box(modifier = Modifier.fillMaxWidth().height(160.dp)) {
            if (hasData) {
                Canvas(modifier = Modifier.fillMaxWidth().height(160.dp)) {
                    val chartLeft = 8f
                    val chartRight = size.width - 8f
                    val chartTop = 8f
                    val chartBottom = size.height - 8f
                    val chartWidth = chartRight - chartLeft
                    val chartHeight = chartBottom - chartTop

                    fun xOf(index: Int, total: Int): Float =
                        chartLeft + (index.toFloat() / (total - 1).coerceAtLeast(1)) * chartWidth

                    fun yOf(level: Double): Float =
                        chartBottom - (level.toFloat() / 100f).coerceIn(0f, 1f) * chartHeight

                    // threshold line
                    val threshY = yOf(reorderThresholdPct.toDouble())
                    val dashEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 4f))
                    drawLine(
                        color = stateColor.copy(alpha = 0.4f),
                        start = Offset(chartLeft, threshY),
                        end = Offset(chartRight, threshY),
                        strokeWidth = 1.5f,
                        pathEffect = dashEffect,
                    )

                    // today divider
                    val todayX = if (historical.isNotEmpty() && forecast.isNotEmpty()) {
                        xOf(historical.size - 1, all.size)
                    } else null
                    if (todayX != null) {
                        drawLine(
                            color = stateColor.copy(alpha = 0.35f),
                            start = Offset(todayX, chartTop),
                            end = Offset(todayX, chartBottom),
                            strokeWidth = 1.5f,
                            pathEffect = dashEffect,
                        )
                    }

                    // filled area (historical solid, forecast lighter)
                    if (historical.size >= 2) {
                        drawFilledSegment(historical, all, chartLeft, chartBottom, chartHeight, chartWidth,
                            stateColor.copy(alpha = 0.25f), 0)
                    }
                    if (forecast.size >= 2 && historical.isNotEmpty()) {
                        drawFilledSegment(forecast, all, chartLeft, chartBottom, chartHeight, chartWidth,
                            stateColor.copy(alpha = 0.12f), historical.size - 1)
                    }

                    // historical line (solid)
                    if (historical.size >= 2) {
                        val path = Path()
                        historical.forEachIndexed { i, p ->
                            val x = xOf(i, all.size)
                            val y = yOf(p.level_pct)
                            if (i == 0) path.moveTo(x, y)
                            else {
                                val px = xOf(i - 1, all.size)
                                val py = yOf(historical[i - 1].level_pct)
                                path.cubicTo(px + (x - px) * 0.4f, py, x - (x - px) * 0.4f, y, x, y)
                            }
                        }
                        drawPath(path, color = stateColor, style = Stroke(width = 3f, cap = StrokeCap.Round))
                    }

                    // forecast line (dashed)
                    if (forecast.size >= 2 && historical.isNotEmpty()) {
                        val forecastDash = PathEffect.dashPathEffect(floatArrayOf(12f, 6f))
                        val path = Path()
                        val offset = historical.size - 1
                        forecast.forEachIndexed { i, p ->
                            val x = xOf(offset + i, all.size)
                            val y = yOf(p.level_pct)
                            if (i == 0) path.moveTo(x, y)
                            else {
                                val px = xOf(offset + i - 1, all.size)
                                val py = yOf(forecast[i - 1].level_pct)
                                path.cubicTo(px + (x - px) * 0.4f, py, x - (x - px) * 0.4f, y, x, y)
                            }
                        }
                        drawPath(path, color = stateColor.copy(alpha = 0.6f),
                            style = Stroke(width = 2.5f, cap = StrokeCap.Round, pathEffect = forecastDash))
                    }
                }
            }

            // callout box overlay
            if (calloutContent != null) {
                Surface(
                    modifier = Modifier.align(Alignment.TopEnd).padding(4.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp),
                    tonalElevation = 2.dp,
                ) { calloutContent() }
            }
        }

        // X-axis labels
        val leftLabel = historical.firstOrNull()?.timestamp?.let { fmtDate(it) } ?: ""
        val rightLabel = if (status == "ok") {
            forecast.lastOrNull()?.timestamp?.let { "Run out\n${fmtDate(it)}" } ?: "Run out\n—"
        } else "Run out\n—"
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceBetween,
        ) {
            Text(leftLabel, style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
            Text(rightLabel, style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                textAlign = androidx.compose.ui.text.style.TextAlign.End)
        }
    }
}

private fun DrawScope.drawFilledSegment(
    points: List<ForecastPoint>,
    all: List<ForecastPoint>,
    chartLeft: Float,
    chartBottom: Float,
    chartHeight: Float,
    chartWidth: Float,
    fillColor: Color,
    indexOffset: Int,
) {
    val total = all.size

    fun xOf(index: Int): Float =
        chartLeft + (index.toFloat() / (total - 1).coerceAtLeast(1)) * chartWidth

    fun yOf(level: Double): Float =
        chartBottom - (level.toFloat() / 100f).coerceIn(0f, 1f) * chartHeight

    val fillPath = Path()
    val firstX = xOf(indexOffset)
    fillPath.moveTo(firstX, chartBottom)
    points.forEachIndexed { i, p ->
        val x = xOf(indexOffset + i)
        val y = yOf(p.level_pct)
        if (i == 0) fillPath.lineTo(x, y)
        else {
            val px = xOf(indexOffset + i - 1)
            val py = yOf(points[i - 1].level_pct)
            fillPath.cubicTo(px + (x - px) * 0.4f, py, x - (x - px) * 0.4f, y, x, y)
        }
    }
    val lastX = xOf(indexOffset + points.size - 1)
    fillPath.lineTo(lastX, chartBottom)
    fillPath.close()
    drawPath(fillPath, color = fillColor)
}
```

- [ ] **Step 2: Build the full app**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :app:assembleDebug 2>&1 | tail -8
```

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Run all Android tests**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:home:test 2>&1 | tail -10
```

Expected: 8 tests pass.

- [ ] **Step 4: Install on device and visually verify**

```bash
~/Library/Android/sdk/platform-tools/adb -s 58071FDCQ002LU install -r /Users/sdagguba/kibble-reorder/android/app/build/outputs/apk/debug/app-debug.apk && ~/Library/Android/sdk/platform-tools/adb -s 58071FDCQ002LU reverse tcp:8000 tcp:8000
```

Open the app. Verify:
- Container fill changes color based on state (green = stocked, orange = reorder soon, red = reorder now)
- Subtitle shows a meaningful message (not "Calibrating…")
- Forecast card shows badge pill with colored dot and label
- Chart shows filled area and, when there's forecast data, a dashed future line

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add android/feature/home/src/main/kotlin/com/kibble/feature/home/components/ForecastChart.kt && git commit -m "feat(android): ForecastChart redesign — filled area, dashed forecast, callout box, state-driven colors"
```

---

## Final check

- [ ] **Run all backend tests**

```bash
cd /Users/sdagguba/kibble-reorder/backend && .venv/bin/pytest -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Run all Android tests**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew test 2>&1 | grep -E "tests|PASSED|FAILED|BUILD" | tail -10
```

Expected: all pass, BUILD SUCCESSFUL.
