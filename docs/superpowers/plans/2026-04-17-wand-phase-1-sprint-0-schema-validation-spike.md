# Wand Phase 1 — Sprint 0: Schema Validation Spike — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stress-test the Phase 1 v0 data model (spec §8) against real scraped product data from Tier 1 retailers, produce a field-quality scorecard + evidence-backed v1 schema, and seed a Postgres instance with samples so downstream sprints can begin migrations from an empirically validated foundation.

**Architecture:** A disposable Python workspace under `spike/` with two samplers (Tier 0 Shopify `/products.json` for D2C brands, Tier 1 Playwright+proxy for marketplaces), a scorecard generator that builds a field matrix and quality scores from the samples, a v1 schema evolved from v0 with evidence citations, and a seed script that loads the samples into Postgres to verify core queries (price compare, shelf reads, search). The spike code is not production — it is discarded after the spike; only the v1 schema, scorecard, and decision memo survive into Sprint 1.

**Tech Stack:** Python 3.12, uv (package manager), Pydantic v2 (typed models for captures), httpx (Shopify fetches), Playwright (headful Chromium for marketplaces), playwright-stealth, a residential-proxy vendor (Bright Data trial or Smartproxy pay-as-you-go), pytest + pytest-asyncio, psycopg 3 + SQLAlchemy Core, PostgreSQL 16 (via docker-compose), ruff + mypy, python-dotenv.

**Spec reference:** `docs/superpowers/specs/2026-04-17-wand-phase-1-catalog-shelf-design.md` §8 (data model v0), §9 (scraping architecture), §11 (this sprint), §15 (empirical samples already gathered during brainstorming).

**Deliverables at sprint end:**
1. `spike/data/reports/field-matrix.csv` — field × retailer presence matrix across 80 samples
2. `spike/data/reports/scorecard.md` — field-quality scorecard (reliably present / often missing / always imputed)
3. `spike/schema/v1.sql` — evolved schema with evidence-citation comments per non-obvious decision
4. `spike/memo/decision-memo.md` — 5-page memo explaining v0→v1 deltas
5. Seeded Postgres instance verifying the 3 canonical query patterns

**Non-goals:** No production ingestion. No web frontend. No auth. No migrations framework yet (Alembic comes in Sprint 1). No Temporal. No Redis. No frontend of any kind. We are only validating the data model.

---

## File Structure

```
sasank-playground/
├── docker-compose.yml              # Postgres 16 for the spike (no Redis yet)
├── spike/
│   ├── README.md                   # How to run the spike end-to-end
│   ├── pyproject.toml              # uv-managed deps
│   ├── uv.lock
│   ├── .env.example                # PROXY_URL, PROXY_USER, PROXY_PASS, DATABASE_URL
│   ├── src/spike/
│   │   ├── __init__.py
│   │   ├── config.py               # Retailer registry (Tier 0 vs Tier 1, URLs, selectors)
│   │   ├── models.py               # Pydantic: RawCapture, ParsedSample, FieldPresence
│   │   ├── samplers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Sampler protocol + shared helpers
│   │   │   ├── shopify.py          # Tier 0: /products.json
│   │   │   └── marketplace.py      # Tier 1: Playwright + stealth + proxy
│   │   ├── scorecard/
│   │   │   ├── __init__.py
│   │   │   ├── analyze.py          # Build field matrix + presence stats
│   │   │   └── render.py           # Emit CSV + markdown
│   │   └── schema/
│   │       ├── __init__.py
│   │       ├── v0.sql              # Copied from spec §8 verbatim (baseline)
│   │       ├── v1.sql              # Evolved schema (Task 9)
│   │       └── seed.py             # Load parsed samples into v1 Postgres
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_config.py
│   │   ├── test_shopify_sampler.py
│   │   ├── test_marketplace_sampler.py
│   │   ├── test_scorecard_analyze.py
│   │   ├── test_scorecard_render.py
│   │   └── test_schema_queries.py  # Verifies price-compare, shelf-read, search
│   ├── scripts/
│   │   ├── run_sample_crawl.py     # Drives all samplers, writes data/raw + data/parsed
│   │   ├── build_reports.py        # Runs scorecard over data/parsed
│   │   └── seed_and_verify.py      # Creates v1 schema + loads samples + runs queries
│   ├── data/                       # gitignored — local sample outputs
│   │   ├── raw/                    # raw_html/*.html, raw_json/*.json per SKU
│   │   ├── parsed/                 # parsed/*.json per SKU (ParsedSample)
│   │   └── reports/                # field-matrix.csv, scorecard.md
│   └── memo/
│       └── decision-memo.md        # 5-page v0→v1 justification
└── docs/superpowers/plans/
    └── 2026-04-17-wand-phase-1-sprint-0-schema-validation-spike.md   # this file
```

Responsibility split:
- `config.py` — single source of truth for which retailers and which SKU URLs the spike samples. Keeps the crawl reproducible.
- `models.py` — all types shared across samplers, scorecard, and schema seeder. Prevents drift.
- `samplers/` — one file per tier. Each sampler's job is: fetch → persist raw → parse → return `ParsedSample`. No cross-sampler coupling.
- `scorecard/` — pure functions over `list[ParsedSample]`. No network, no DB. Fast to re-run.
- `schema/` — v0 is frozen (copied from spec). v1 emerges from scorecard findings. `seed.py` is the only code that touches Postgres.
- `scripts/` — thin runners that wire the modules. Keeping orchestration out of library code makes tests trivial.

---

## Task 1: Spike workspace scaffold

**Files:**
- Create: `/Users/sdagguba/sasank-playground/spike/pyproject.toml`
- Create: `/Users/sdagguba/sasank-playground/spike/.env.example`
- Create: `/Users/sdagguba/sasank-playground/spike/README.md`
- Create: `/Users/sdagguba/sasank-playground/spike/src/spike/__init__.py`
- Create: `/Users/sdagguba/sasank-playground/spike/tests/__init__.py`
- Create: `/Users/sdagguba/sasank-playground/spike/tests/conftest.py`
- Create: `/Users/sdagguba/sasank-playground/docker-compose.yml`
- Modify: `/Users/sdagguba/sasank-playground/.gitignore` (append `spike/data/`, `spike/.env`)

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "wand-spike"
version = "0.0.1"
description = "Phase 1 Schema Validation Spike — disposable"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2.7",
  "httpx>=0.27",
  "playwright>=1.44",
  "playwright-stealth>=1.0.6",
  "python-dotenv>=1.0",
  "psycopg[binary]>=3.2",
  "sqlalchemy>=2.0",
  "tenacity>=8.3",
  "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "pytest-playwright>=0.5",
  "ruff>=0.4",
  "mypy>=1.10",
  "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra -q"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["spike"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/spike"]
```

- [ ] **Step 2: Write `.env.example`**

```
# Residential proxy (Smartproxy or Bright Data). Required for Tier 1 marketplaces.
PROXY_URL=http://gate.smartproxy.com:10000
PROXY_USER=
PROXY_PASS=

# Postgres — matches docker-compose.yml below.
DATABASE_URL=postgresql+psycopg://wand:wand@localhost:5433/wand_spike

# Headful playwright during dev makes debugging easier.
PLAYWRIGHT_HEADLESS=false

# Cap on total samples per retailer (spec §11 calls for 5–10 per retailer).
SAMPLES_PER_RETAILER=8
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: wand
      POSTGRES_PASSWORD: wand
      POSTGRES_DB: wand_spike
    ports:
      - "5433:5432"
    volumes:
      - wand_spike_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U wand -d wand_spike"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  wand_spike_pgdata:
```

- [ ] **Step 4: Write `README.md`**

```markdown
# Wand Schema Validation Spike

Disposable workspace. Goal: produce an empirically validated v1 schema + scorecard. See plan: `docs/superpowers/plans/2026-04-17-wand-phase-1-sprint-0-schema-validation-spike.md`.

## Setup
```
cd spike
cp .env.example .env        # fill in PROXY_USER + PROXY_PASS
uv sync --extra dev
uv run playwright install chromium
docker compose -f ../docker-compose.yml up -d
```

## Run end-to-end
```
uv run python scripts/run_sample_crawl.py
uv run python scripts/build_reports.py
uv run python scripts/seed_and_verify.py
```

## Tests
```
uv run pytest
```
```

- [ ] **Step 5: Write empty package markers + conftest**

`src/spike/__init__.py`:
```python
"""Wand Phase 1 Schema Validation Spike — disposable."""
```

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

SPIKE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SPIKE_ROOT / ".env", override=False)


@pytest.fixture()
def spike_root() -> Path:
    return SPIKE_ROOT


@pytest.fixture()
def sample_fixture_dir(spike_root: Path) -> Path:
    d = spike_root / "tests" / "fixtures"
    d.mkdir(exist_ok=True)
    return d
```

- [ ] **Step 6: Update `.gitignore`**

Append to `/Users/sdagguba/sasank-playground/.gitignore`:

```
# Spike local artifacts (raw HTML, parsed JSON, reports) — regenerate on demand
spike/data/
spike/.env
spike/.venv/
spike/uv.lock
```

- [ ] **Step 7: Install + sanity-check**

Run:
```
cd /Users/sdagguba/sasank-playground/spike
uv sync --extra dev
uv run python -c "import spike; print(spike.__doc__)"
```
Expected: prints the docstring "Wand Phase 1 Schema Validation Spike — disposable."

- [ ] **Step 8: Commit**

```
cd /Users/sdagguba/sasank-playground
git add spike/pyproject.toml spike/.env.example spike/README.md \
        spike/src/spike/__init__.py spike/tests/__init__.py spike/tests/conftest.py \
        docker-compose.yml .gitignore
git commit -m "spike: scaffold schema validation spike workspace"
```

---

## Task 2: Retailer registry + typed models

**Files:**
- Create: `spike/src/spike/config.py`
- Create: `spike/src/spike/models.py`
- Create: `spike/tests/test_config.py`

- [ ] **Step 1: Write the failing test `tests/test_config.py`**

```python
from __future__ import annotations

from spike.config import RETAILERS, RetailerTier, retailer_by_slug


def test_registry_has_all_tier1_retailers() -> None:
    expected = {
        "nykaa", "amazon_in", "tira", "purplle",
        "minimalist", "plum", "mcaffeine", "dot_and_key", "the_derma_co",
    }
    assert {r.slug for r in RETAILERS} == expected


def test_shopify_retailers_have_products_json_url() -> None:
    shopify = [r for r in RETAILERS if r.tier is RetailerTier.SHOPIFY]
    assert len(shopify) == 5
    for r in shopify:
        assert r.products_json_url is not None
        assert r.products_json_url.endswith("/products.json")


def test_marketplace_retailers_have_sample_urls() -> None:
    marketplaces = [r for r in RETAILERS if r.tier is RetailerTier.MARKETPLACE]
    assert len(marketplaces) == 4
    for r in marketplaces:
        assert len(r.sample_product_urls) >= 8, f"{r.slug} needs >=8 sample URLs"


def test_retailer_by_slug_roundtrip() -> None:
    assert retailer_by_slug("nykaa").name == "Nykaa"
```

- [ ] **Step 2: Run test — expect fail**

```
cd /Users/sdagguba/sasank-playground/spike
uv run pytest tests/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'spike.config'` (or similar import error).

- [ ] **Step 3: Write `src/spike/config.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RetailerTier(str, Enum):
    SHOPIFY = "shopify"          # Tier 0 in spec §9.2
    MARKETPLACE = "marketplace"  # Tier 1


@dataclass(frozen=True)
class Retailer:
    slug: str
    name: str
    tier: RetailerTier
    base_url: str
    products_json_url: str | None = None       # Shopify only
    sample_product_urls: tuple[str, ...] = field(default_factory=tuple)  # Marketplace only
    needs_proxy: bool = False


RETAILERS: tuple[Retailer, ...] = (
    # --- Shopify D2C (Tier 0) ---
    Retailer(
        slug="minimalist", name="Minimalist", tier=RetailerTier.SHOPIFY,
        base_url="https://beminimalist.co",
        products_json_url="https://beminimalist.co/products.json",
    ),
    Retailer(
        slug="plum", name="Plum Goodness", tier=RetailerTier.SHOPIFY,
        base_url="https://plumgoodness.com",
        products_json_url="https://plumgoodness.com/products.json",
    ),
    Retailer(
        slug="mcaffeine", name="mCaffeine", tier=RetailerTier.SHOPIFY,
        base_url="https://mcaffeine.com",
        products_json_url="https://mcaffeine.com/products.json",
    ),
    Retailer(
        slug="dot_and_key", name="Dot & Key", tier=RetailerTier.SHOPIFY,
        base_url="https://dotandkey.com",
        products_json_url="https://dotandkey.com/products.json",
    ),
    Retailer(
        slug="the_derma_co", name="The Derma Co", tier=RetailerTier.SHOPIFY,
        base_url="https://thedermaco.com",
        products_json_url="https://thedermaco.com/products.json",
    ),
    # --- Marketplaces (Tier 1) ---
    Retailer(
        slug="nykaa", name="Nykaa", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.nykaa.com",
        sample_product_urls=(
            # Curator should replace these with real URLs before running the crawl.
            # Picks should span skin / hair / body and price tiers.
            "https://www.nykaa.com/REPLACE-skincare-1",
            "https://www.nykaa.com/REPLACE-skincare-2",
            "https://www.nykaa.com/REPLACE-skincare-3",
            "https://www.nykaa.com/REPLACE-haircare-1",
            "https://www.nykaa.com/REPLACE-haircare-2",
            "https://www.nykaa.com/REPLACE-haircare-3",
            "https://www.nykaa.com/REPLACE-bodycare-1",
            "https://www.nykaa.com/REPLACE-bodycare-2",
        ),
        needs_proxy=True,
    ),
    Retailer(
        slug="amazon_in", name="Amazon.in", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.amazon.in",
        sample_product_urls=(
            "https://www.amazon.in/dp/REPLACE1",
            "https://www.amazon.in/dp/REPLACE2",
            "https://www.amazon.in/dp/REPLACE3",
            "https://www.amazon.in/dp/REPLACE4",
            "https://www.amazon.in/dp/REPLACE5",
            "https://www.amazon.in/dp/REPLACE6",
            "https://www.amazon.in/dp/REPLACE7",
            "https://www.amazon.in/dp/REPLACE8",
        ),
        needs_proxy=True,
    ),
    Retailer(
        slug="tira", name="Tira", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.tirabeauty.com",
        sample_product_urls=tuple(f"https://www.tirabeauty.com/product/REPLACE{i}" for i in range(8)),
        needs_proxy=True,
    ),
    Retailer(
        slug="purplle", name="Purplle", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.purplle.com",
        sample_product_urls=tuple(f"https://www.purplle.com/product/REPLACE{i}" for i in range(8)),
        needs_proxy=True,
    ),
)


_BY_SLUG = {r.slug: r for r in RETAILERS}


def retailer_by_slug(slug: str) -> Retailer:
    return _BY_SLUG[slug]
```

> **Note on REPLACE URLs:** these are placeholders. Before running the crawl in Task 5, a curator (or Sasank) picks 8 real product URLs per marketplace spanning skin/hair/body. This is a deliberate manual step — the sample is only meaningful if the products are diverse. Record picks in `spike/data/sample-urls.csv` alongside the crawl output.

- [ ] **Step 4: Run test — expect pass**

```
uv run pytest tests/test_config.py -v
```
Expected: all 4 tests pass.

- [ ] **Step 5: Write the failing test for models — `tests/test_models.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from spike.models import ParsedSample, RawCapture


def test_raw_capture_roundtrip_json() -> None:
    rc = RawCapture(
        retailer_slug="minimalist",
        source_url="https://beminimalist.co/products/niacinamide",
        tier_used="shopify",
        fetched_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        fetcher_version="spike-0.0.1",
        content_type="application/json",
        body="{\"product\": {}}",
        http_status=200,
    )
    blob = rc.model_dump_json()
    restored = RawCapture.model_validate_json(blob)
    assert restored == rc


def test_parsed_sample_tracks_missing_fields_explicitly() -> None:
    ps = ParsedSample(
        retailer_slug="nykaa",
        source_url="https://www.nykaa.com/x",
        raw_capture_id="abc123",
        canonical_name="Example serum",
        brand_name="Brand",
        category_hint="face",
        current_price=None,
        current_price_raw="Currently unavailable",
        compare_at_price=None,
        stock_status_raw=None,
        variants=[],
        ingredients_raw=None,
        ingredients_source=None,
        description_raw=None,
        images=[],
        rating_raw=None,
        offers_raw=[],
        missing_fields={"current_price", "stock_status", "ingredients", "rating"},
    )
    assert "current_price" in ps.missing_fields
    assert ps.current_price_raw == "Currently unavailable"
```

- [ ] **Step 6: Run model test — expect fail**

```
uv run pytest tests/test_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'spike.models'`.

- [ ] **Step 7: Write `src/spike/models.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TierLabel = Literal["shopify", "marketplace-selector", "marketplace-html"]


class RawCapture(BaseModel):
    """Immutable verbatim capture of a source response.

    Mirrors spec §8 RawScrapes. Spike stores these in `data/raw/<retailer>/<id>.json`.
    """

    retailer_slug: str
    source_url: str
    tier_used: TierLabel
    fetched_at: datetime
    fetcher_version: str
    content_type: str
    body: str                       # HTML text or JSON text — source of truth
    http_status: int


class Variant(BaseModel):
    option_name: str | None = None  # e.g. "Size", "Shade"
    option_value: str | None = None
    sku: str | None = None
    price: float | None = None
    compare_at_price: float | None = None
    available: bool | None = None


class ParsedSample(BaseModel):
    """What each sampler produces.

    Fields tracked explicitly even when missing — the scorecard measures absence.
    """

    retailer_slug: str
    source_url: str
    raw_capture_id: str

    # Identity
    canonical_name: str | None = None
    brand_name: str | None = None
    category_hint: str | None = None       # raw retailer category/breadcrumb

    # Price
    current_price: float | None = None
    current_price_raw: str | None = None   # the literal string scraped
    compare_at_price: float | None = None

    # Stock
    stock_status_raw: str | None = None

    # Variants
    variants: list[Variant] = Field(default_factory=list)

    # Ingredients
    ingredients_raw: str | None = None
    ingredients_source: Literal["text", "image", "pdf", None] = None

    # Description / media
    description_raw: str | None = None
    images: list[str] = Field(default_factory=list)

    # Reviews
    rating_raw: str | None = None

    # Offers
    offers_raw: list[str] = Field(default_factory=list)

    # Explicit absence set — fuels the scorecard
    missing_fields: set[str] = Field(default_factory=set)


class FieldPresence(BaseModel):
    """Row in the field × retailer matrix."""

    field_name: str
    retailer_slug: str
    present_count: int
    sample_count: int
    notes: str | None = None

    @property
    def presence_ratio(self) -> float:
        return self.present_count / self.sample_count if self.sample_count else 0.0
```

- [ ] **Step 8: Run model test — expect pass**

```
uv run pytest tests/test_models.py -v
```
Expected: both tests pass.

- [ ] **Step 9: Commit**

```
git add spike/src/spike/config.py spike/src/spike/models.py \
        spike/tests/test_config.py spike/tests/test_models.py
git commit -m "spike: retailer registry + parsed-sample/raw-capture models"
```

---

## Task 3: Shopify sampler (Tier 0)

**Files:**
- Create: `spike/src/spike/samplers/__init__.py`
- Create: `spike/src/spike/samplers/base.py`
- Create: `spike/src/spike/samplers/shopify.py`
- Create: `spike/tests/test_shopify_sampler.py`
- Create: `spike/tests/fixtures/minimalist_products.json` (saved during development)

- [ ] **Step 1: Write `samplers/__init__.py` + `samplers/base.py` (shared scaffolding)**

`samplers/__init__.py`:
```python
```

`samplers/base.py`:
```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from spike.models import ParsedSample, RawCapture


def capture_id(rc: RawCapture) -> str:
    """Stable ID derived from source_url + fetched_at — used as filename."""
    key = f"{rc.retailer_slug}:{rc.source_url}:{rc.fetched_at.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def persist_raw(rc: RawCapture, raw_dir: Path) -> str:
    cid = capture_id(rc)
    retailer_dir = raw_dir / rc.retailer_slug
    retailer_dir.mkdir(parents=True, exist_ok=True)
    (retailer_dir / f"{cid}.json").write_text(rc.model_dump_json(indent=2))
    return cid


def persist_parsed(ps: ParsedSample, parsed_dir: Path) -> None:
    retailer_dir = parsed_dir / ps.retailer_slug
    retailer_dir.mkdir(parents=True, exist_ok=True)
    (retailer_dir / f"{ps.raw_capture_id}.json").write_text(ps.model_dump_json(indent=2))


class Sampler(Protocol):
    """A sampler produces ParsedSample instances and persists RawCapture side-effects."""

    async def sample(self, n: int, raw_dir: Path, parsed_dir: Path) -> list[ParsedSample]: ...
```

- [ ] **Step 2: Write the failing test `tests/test_shopify_sampler.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from spike.samplers.shopify import ShopifySampler


@pytest.fixture()
def minimalist_fixture(sample_fixture_dir: Path) -> Path:
    """A minimal but realistic /products.json payload — 2 products with variant + ingredients shapes."""
    path = sample_fixture_dir / "minimalist_products.json"
    if not path.exists():
        path.write_text(json.dumps({
            "products": [
                {
                    "id": 1,
                    "title": "Niacinamide 10% Face Serum",
                    "vendor": "Minimalist",
                    "product_type": "Serum",
                    "handle": "niacinamide-10",
                    "body_html": "<p>Balances oil. Fades marks.</p>",
                    "tags": "face,serum,oily-skin",
                    "images": [{"src": "https://cdn.shopify.com/img/niacinamide.jpg"}],
                    "variants": [
                        {"id": 10, "title": "Default Title", "price": "449.00",
                         "compare_at_price": "549.00", "available": True, "sku": "NIA-10-30"}
                    ],
                },
                {
                    "id": 2,
                    "title": "Salicylic Acid 2% Face Wash",
                    "vendor": "Minimalist",
                    "product_type": "",   # deliberately blank — validates taxonomy stress-point
                    "handle": "salicylic-2",
                    "body_html": "",       # deliberately empty — validates fallback need
                    "tags": "",
                    "images": [],
                    "variants": [
                        {"id": 20, "title": "100ml", "price": "299.00",
                         "compare_at_price": None, "available": True, "sku": "SAL-2-100"},
                        {"id": 21, "title": "50ml", "price": "179.00",
                         "compare_at_price": None, "available": False, "sku": "SAL-2-50"},
                    ],
                },
            ]
        }))
    return path


@respx.mock
async def test_shopify_sampler_returns_n_parsed_samples(
    minimalist_fixture: Path, tmp_path: Path
) -> None:
    body = minimalist_fixture.read_text()
    respx.get("https://beminimalist.co/products.json").mock(
        return_value=Response(200, text=body, headers={"content-type": "application/json"})
    )

    raw_dir = tmp_path / "raw"
    parsed_dir = tmp_path / "parsed"
    sampler = ShopifySampler(retailer_slug="minimalist")

    samples = await sampler.sample(n=2, raw_dir=raw_dir, parsed_dir=parsed_dir)

    assert len(samples) == 2
    names = {s.canonical_name for s in samples}
    assert names == {"Niacinamide 10% Face Serum", "Salicylic Acid 2% Face Wash"}

    # Raw capture persisted once (the whole /products.json fetch), not per-product.
    raw_files = list((raw_dir / "minimalist").glob("*.json"))
    assert len(raw_files) == 1

    # Parsed files: one per product.
    parsed_files = list((parsed_dir / "minimalist").glob("*.json"))
    assert len(parsed_files) == 2


@respx.mock
async def test_shopify_sampler_marks_missing_fields(
    minimalist_fixture: Path, tmp_path: Path
) -> None:
    body = minimalist_fixture.read_text()
    respx.get("https://beminimalist.co/products.json").mock(
        return_value=Response(200, text=body)
    )

    sampler = ShopifySampler(retailer_slug="minimalist")
    samples = await sampler.sample(n=2, raw_dir=tmp_path / "raw", parsed_dir=tmp_path / "parsed")

    salicylic = next(s for s in samples if s.canonical_name.startswith("Salicylic"))
    assert "description" in salicylic.missing_fields
    assert "category_hint" in salicylic.missing_fields
    # Shopify never exposes ingredients structurally → always missing from this tier.
    assert "ingredients" in salicylic.missing_fields


@respx.mock
async def test_shopify_sampler_captures_multi_variant_product(
    minimalist_fixture: Path, tmp_path: Path
) -> None:
    body = minimalist_fixture.read_text()
    respx.get("https://beminimalist.co/products.json").mock(
        return_value=Response(200, text=body)
    )
    sampler = ShopifySampler(retailer_slug="minimalist")
    samples = await sampler.sample(n=2, raw_dir=tmp_path / "raw", parsed_dir=tmp_path / "parsed")

    salicylic = next(s for s in samples if s.canonical_name.startswith("Salicylic"))
    assert len(salicylic.variants) == 2
    sizes = {v.option_value for v in salicylic.variants}
    assert sizes == {"100ml", "50ml"}
```

- [ ] **Step 3: Run test — expect fail**

```
uv run pytest tests/test_shopify_sampler.py -v
```
Expected: `ModuleNotFoundError: No module named 'spike.samplers.shopify'`.

- [ ] **Step 4: Write `src/spike/samplers/shopify.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from spike.config import retailer_by_slug
from spike.models import ParsedSample, RawCapture, Variant
from spike.samplers.base import persist_parsed, persist_raw

_FETCHER_VERSION = "spike-shopify-0.0.1"


class ShopifySampler:
    """Tier 0: reads Shopify's open /products.json endpoint.

    Ingredients are never structurally exposed by Shopify — always a miss here,
    which the scorecard will capture as an evidence data point.
    """

    def __init__(self, retailer_slug: str) -> None:
        self.retailer = retailer_by_slug(retailer_slug)
        if self.retailer.products_json_url is None:
            raise ValueError(f"{retailer_slug} is not a Shopify retailer")

    async def sample(
        self, n: int, raw_dir: Path, parsed_dir: Path
    ) -> list[ParsedSample]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self.retailer.products_json_url)
            resp.raise_for_status()

        rc = RawCapture(
            retailer_slug=self.retailer.slug,
            source_url=self.retailer.products_json_url or "",
            tier_used="shopify",
            fetched_at=datetime.now(timezone.utc),
            fetcher_version=_FETCHER_VERSION,
            content_type=resp.headers.get("content-type", "application/json"),
            body=resp.text,
            http_status=resp.status_code,
        )
        cid = persist_raw(rc, raw_dir)

        payload = json.loads(resp.text)
        products = payload.get("products", [])[:n]

        samples: list[ParsedSample] = []
        for p in products:
            ps = self._parse_product(p, cid)
            persist_parsed(ps, parsed_dir)
            samples.append(ps)
        return samples

    def _parse_product(self, p: dict[str, Any], raw_capture_id: str) -> ParsedSample:
        missing: set[str] = set()

        canonical_name = p.get("title") or None
        if not canonical_name:
            missing.add("canonical_name")

        brand_name = p.get("vendor") or None

        category_hint = p.get("product_type") or None
        if not category_hint:
            missing.add("category_hint")

        description_raw = p.get("body_html") or None
        if not description_raw:
            missing.add("description")

        images = [img["src"] for img in (p.get("images") or []) if img.get("src")]
        if not images:
            missing.add("images")

        variants_raw = p.get("variants") or []
        variants = [
            Variant(
                option_name=None if v.get("title") in (None, "Default Title") else "Size/Option",
                option_value=None if v.get("title") == "Default Title" else v.get("title"),
                sku=v.get("sku") or None,
                price=float(v["price"]) if v.get("price") else None,
                compare_at_price=float(v["compare_at_price"]) if v.get("compare_at_price") else None,
                available=v.get("available"),
            )
            for v in variants_raw
        ]

        first = variants[0] if variants else None
        current_price = first.price if first else None
        current_price_raw = variants_raw[0].get("price") if variants_raw else None
        compare_at_price = first.compare_at_price if first else None
        if current_price is None:
            missing.add("current_price")

        # Shopify /products.json never exposes ingredients structurally.
        missing.add("ingredients")
        # /products.json has `available` per variant but not numeric stock / low-stock hint.
        stock_status_raw = (
            "in_stock" if any(v.get("available") for v in variants_raw) else "out_of_stock"
        )
        # Rating is never in /products.json.
        missing.add("rating")

        return ParsedSample(
            retailer_slug=self.retailer.slug,
            source_url=f"{self.retailer.base_url}/products/{p.get('handle', '')}",
            raw_capture_id=raw_capture_id,
            canonical_name=canonical_name,
            brand_name=brand_name,
            category_hint=category_hint,
            current_price=current_price,
            current_price_raw=str(current_price_raw) if current_price_raw else None,
            compare_at_price=compare_at_price,
            stock_status_raw=stock_status_raw,
            variants=variants,
            description_raw=description_raw,
            images=images,
            missing_fields=missing,
        )
```

- [ ] **Step 5: Run test — expect pass**

```
uv run pytest tests/test_shopify_sampler.py -v
```
Expected: all 3 tests pass.

- [ ] **Step 6: Live-sanity-check against real Minimalist endpoint (manual, no assertion)**

Run:
```
uv run python -c "
import asyncio
from pathlib import Path
from spike.samplers.shopify import ShopifySampler

async def main():
    s = ShopifySampler('minimalist')
    samples = await s.sample(n=3, raw_dir=Path('data/raw'), parsed_dir=Path('data/parsed'))
    for x in samples:
        print(x.canonical_name, x.current_price, sorted(x.missing_fields))
asyncio.run(main())
"
```
Expected: 3 product titles printed with non-None prices and `{'ingredients', 'rating'}` in the missing sets. This confirms the parser works end-to-end against the live endpoint before we trust it in the full crawl.

- [ ] **Step 7: Commit**

```
git add spike/src/spike/samplers/__init__.py spike/src/spike/samplers/base.py \
        spike/src/spike/samplers/shopify.py spike/tests/test_shopify_sampler.py \
        spike/tests/fixtures/minimalist_products.json
git commit -m "spike: tier-0 shopify sampler with variant + missing-field tracking"
```

---

## Task 4: Marketplace sampler (Tier 1) with proxy + stealth

**Files:**
- Create: `spike/src/spike/samplers/marketplace.py`
- Create: `spike/tests/test_marketplace_sampler.py`
- Create: `spike/tests/fixtures/nykaa_sample.html` (handcrafted minimal HTML for unit tests)

> **Design note:** this sampler is the most fragile part of the spike. Spec §9.6 calls out that Nykaa/Amazon/Tira/Purplle aggressively block basic requests — so we implement with proxy + playwright-stealth from the start. Selectors here are deliberately conservative: we only attempt **price**, **title**, **stock**, **ingredients-if-in-DOM**, **rating**, **offer-strings**. Anything we can't extract confidently goes into `missing_fields`, not guessed. That's the whole point of the spike — learn *what's missing*, not fake completeness.

- [ ] **Step 1: Write handcrafted HTML fixture `tests/fixtures/nykaa_sample.html`**

```html
<!doctype html>
<html><head><title>Sample Product — Nykaa</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Sample Face Serum",
 "brand":{"@type":"Brand","name":"SampleBrand"},
 "image":"https://images-static.nykaa.com/sample.jpg",
 "offers":{"@type":"Offer","price":"499","priceCurrency":"INR","availability":"https://schema.org/InStock"},
 "aggregateRating":{"@type":"AggregateRating","ratingValue":"4.3","reviewCount":"212"}
}
</script></head>
<body>
  <h1 class="css-1gc4x7i">Sample Face Serum</h1>
  <div class="css-price">₹499 <span class="css-strike">₹599</span></div>
  <div class="stock-indicator">In Stock</div>
  <div class="offer-list">
    <span class="offer">Flat 10% on Nykaa Prepaid</span>
    <span class="offer">Buy 2 Get 1 Free</span>
  </div>
  <section id="ingredients">
    Water, Niacinamide, Zinc PCA, Glycerin, Hyaluronic Acid, Sodium Hyaluronate.
  </section>
</body></html>
```

- [ ] **Step 2: Write the failing test `tests/test_marketplace_sampler.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from spike.samplers.marketplace import MarketplaceSampler, parse_marketplace_html


def test_parse_marketplace_html_prefers_json_ld(sample_fixture_dir: Path) -> None:
    html = (sample_fixture_dir / "nykaa_sample.html").read_text()
    ps = parse_marketplace_html(
        html=html,
        retailer_slug="nykaa",
        source_url="https://www.nykaa.com/sample",
        raw_capture_id="fixture-1",
    )
    assert ps.canonical_name == "Sample Face Serum"
    assert ps.brand_name == "SampleBrand"
    assert ps.current_price == 499.0
    assert ps.stock_status_raw == "InStock"
    assert ps.rating_raw == "4.3 (212)"
    assert "Flat 10% on Nykaa Prepaid" in ps.offers_raw
    assert ps.ingredients_raw is not None
    assert "Niacinamide" in ps.ingredients_raw


def test_parse_marketplace_html_marks_missing_on_empty_doc() -> None:
    ps = parse_marketplace_html(
        html="<html><body>nothing here</body></html>",
        retailer_slug="nykaa",
        source_url="https://www.nykaa.com/x",
        raw_capture_id="fixture-2",
    )
    assert ps.canonical_name is None
    assert "canonical_name" in ps.missing_fields
    assert "current_price" in ps.missing_fields
    assert "ingredients" in ps.missing_fields


@pytest.mark.skipif(
    "os.getenv('PROXY_USER') in (None, '')",
    reason="Live marketplace fetch requires proxy creds",
)
async def test_live_nykaa_sample_fetch(tmp_path: Path) -> None:
    """Smoke test — runs only when proxy creds are configured.
    Confirms the proxy + stealth path returns at least one non-empty capture."""
    sampler = MarketplaceSampler(retailer_slug="nykaa", max_samples=1)
    samples = await sampler.sample(
        n=1, raw_dir=tmp_path / "raw", parsed_dir=tmp_path / "parsed"
    )
    assert len(samples) == 1
    # We don't assert field content — the spike's point is to measure what's present.
    raw_files = list((tmp_path / "raw" / "nykaa").glob("*.json"))
    assert raw_files, "expected a raw capture file to be persisted"
```

- [ ] **Step 3: Run test — expect fail**

```
uv run pytest tests/test_marketplace_sampler.py -v
```
Expected: `ModuleNotFoundError: No module named 'spike.samplers.marketplace'`.

- [ ] **Step 4: Write `src/spike/samplers/marketplace.py`**

```python
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from spike.config import retailer_by_slug
from spike.models import ParsedSample, RawCapture
from spike.samplers.base import persist_parsed, persist_raw

log = structlog.get_logger()
_FETCHER_VERSION = "spike-marketplace-0.0.1"


def _json_ld_products(html: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, flags=re.DOTALL | re.IGNORECASE,
    ):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                products.append(item)
    return products


def _first(xs: list[str] | None) -> str | None:
    return xs[0] if xs else None


_OFFER_PATTERN = re.compile(
    r'<span[^>]*class=["\']offer["\'][^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL
)
_INGREDIENTS_PATTERN = re.compile(
    r'<section[^>]*id=["\']ingredients["\'][^>]*>(.*?)</section>', re.IGNORECASE | re.DOTALL
)


def parse_marketplace_html(
    *, html: str, retailer_slug: str, source_url: str, raw_capture_id: str
) -> ParsedSample:
    """Best-effort parse. Fields we cannot confidently extract go into missing_fields."""
    missing: set[str] = set()
    products = _json_ld_products(html)
    product = products[0] if products else {}

    canonical_name = product.get("name") or None
    brand_name = (product.get("brand") or {}).get("name") if isinstance(product.get("brand"), dict) else None
    images = [product["image"]] if isinstance(product.get("image"), str) else []

    offers_obj = product.get("offers")
    current_price: float | None = None
    current_price_raw: str | None = None
    stock_status_raw: str | None = None
    if isinstance(offers_obj, dict):
        raw_price = offers_obj.get("price")
        if raw_price is not None:
            current_price_raw = str(raw_price)
            try:
                current_price = float(raw_price)
            except (TypeError, ValueError):
                current_price = None
        availability = offers_obj.get("availability")
        if isinstance(availability, str):
            stock_status_raw = availability.rsplit("/", 1)[-1]

    rating_raw: str | None = None
    agg = product.get("aggregateRating")
    if isinstance(agg, dict):
        rv, rc = agg.get("ratingValue"), agg.get("reviewCount")
        if rv is not None and rc is not None:
            rating_raw = f"{rv} ({rc})"

    offers_raw = [
        re.sub(r"\s+", " ", m.group(1)).strip()
        for m in _OFFER_PATTERN.finditer(html)
    ]

    ingredients_match = _INGREDIENTS_PATTERN.search(html)
    ingredients_raw: str | None = None
    ingredients_source: Any = None
    if ingredients_match:
        ingredients_raw = re.sub(r"<[^>]+>", "", ingredients_match.group(1)).strip() or None
        ingredients_source = "text" if ingredients_raw else None

    if canonical_name is None: missing.add("canonical_name")
    if brand_name is None: missing.add("brand_name")
    if current_price is None: missing.add("current_price")
    if stock_status_raw is None: missing.add("stock_status")
    if ingredients_raw is None: missing.add("ingredients")
    if rating_raw is None: missing.add("rating")
    if not offers_raw: missing.add("offers")
    if not images: missing.add("images")
    missing.add("category_hint")  # marketplaces expose category via breadcrumb — deferred

    return ParsedSample(
        retailer_slug=retailer_slug,
        source_url=source_url,
        raw_capture_id=raw_capture_id,
        canonical_name=canonical_name,
        brand_name=brand_name,
        current_price=current_price,
        current_price_raw=current_price_raw,
        stock_status_raw=stock_status_raw,
        variants=[],
        ingredients_raw=ingredients_raw,
        ingredients_source=ingredients_source,
        description_raw=None,           # skipped in spike — measured as always-missing
        images=images,
        rating_raw=rating_raw,
        offers_raw=offers_raw,
        missing_fields=missing,
    )


class MarketplaceSampler:
    def __init__(self, retailer_slug: str, max_samples: int | None = None) -> None:
        self.retailer = retailer_by_slug(retailer_slug)
        self.max_samples = max_samples

    async def sample(
        self, n: int, raw_dir: Path, parsed_dir: Path
    ) -> list[ParsedSample]:
        urls = self.retailer.sample_product_urls
        if self.max_samples is not None:
            urls = urls[: self.max_samples]
        urls = urls[:n]

        proxy_config = None
        if self.retailer.needs_proxy:
            proxy_url = os.getenv("PROXY_URL")
            proxy_user = os.getenv("PROXY_USER")
            proxy_pass = os.getenv("PROXY_PASS")
            if proxy_url and proxy_user and proxy_pass:
                proxy_config = {
                    "server": proxy_url,
                    "username": proxy_user,
                    "password": proxy_pass,
                }

        headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"

        samples: list[ParsedSample] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless, proxy=proxy_config)
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
            )
            for url in urls:
                page = await context.new_page()
                await stealth_async(page)
                status = 0
                body = ""
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    status = resp.status if resp else 0
                    await page.wait_for_timeout(2500)  # let lazy-loaded JSON-LD settle
                    body = await page.content()
                except Exception as e:  # noqa: BLE001 — spike logs anything
                    log.warning("marketplace_fetch_failed", retailer=self.retailer.slug, url=url, error=str(e))
                finally:
                    await page.close()

                rc = RawCapture(
                    retailer_slug=self.retailer.slug,
                    source_url=url,
                    tier_used="marketplace-selector",
                    fetched_at=datetime.now(timezone.utc),
                    fetcher_version=_FETCHER_VERSION,
                    content_type="text/html",
                    body=body,
                    http_status=status,
                )
                cid = persist_raw(rc, raw_dir)

                ps = parse_marketplace_html(
                    html=body, retailer_slug=self.retailer.slug,
                    source_url=url, raw_capture_id=cid,
                )
                persist_parsed(ps, parsed_dir)
                samples.append(ps)

            await browser.close()
        return samples
```

- [ ] **Step 5: Run test — expect pass**

```
uv run pytest tests/test_marketplace_sampler.py -v
```
Expected: the two `parse_marketplace_html` tests pass; the live one skips unless proxy creds are set.

- [ ] **Step 6: Commit**

```
git add spike/src/spike/samplers/marketplace.py spike/tests/test_marketplace_sampler.py \
        spike/tests/fixtures/nykaa_sample.html
git commit -m "spike: tier-1 marketplace sampler with proxy + stealth + json-ld parser"
```

---

## Task 5: Run the sample crawl — produce 80 real captures

**Files:**
- Create: `spike/scripts/run_sample_crawl.py`
- Create: `spike/data/sample-urls.csv` (curator-populated, manually)

- [ ] **Step 1: Write the driver `scripts/run_sample_crawl.py`**

```python
"""Drive all samplers end-to-end. Writes data/raw/ + data/parsed/.

Usage:
  uv run python scripts/run_sample_crawl.py           # full 80-sample crawl
  uv run python scripts/run_sample_crawl.py --dry     # only Shopify (no proxy needed)
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import structlog
from dotenv import load_dotenv

from spike.config import RETAILERS, RetailerTier
from spike.samplers.marketplace import MarketplaceSampler
from spike.samplers.shopify import ShopifySampler

SPIKE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SPIKE_ROOT / ".env")
log = structlog.get_logger()


async def main(dry: bool) -> None:
    n = int(os.getenv("SAMPLES_PER_RETAILER", "8"))
    raw_dir = SPIKE_ROOT / "data" / "raw"
    parsed_dir = SPIKE_ROOT / "data" / "parsed"

    for r in RETAILERS:
        if r.tier is RetailerTier.SHOPIFY:
            log.info("sampling_shopify", retailer=r.slug, n=n)
            sampler = ShopifySampler(r.slug)
            samples = await sampler.sample(n, raw_dir, parsed_dir)
            log.info("sampled", retailer=r.slug, count=len(samples))
        elif r.tier is RetailerTier.MARKETPLACE:
            if dry:
                log.info("skipping_marketplace_in_dry_mode", retailer=r.slug)
                continue
            log.info("sampling_marketplace", retailer=r.slug, n=n)
            sampler = MarketplaceSampler(r.slug)
            samples = await sampler.sample(n, raw_dir, parsed_dir)
            log.info("sampled", retailer=r.slug, count=len(samples))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="Shopify-only; no marketplaces")
    args = ap.parse_args()
    asyncio.run(main(dry=args.dry))
```

- [ ] **Step 2: Curator picks real sample URLs**

Manual (Sasank or curator): edit `spike/src/spike/config.py` to replace each `REPLACE` URL with a real product URL. Pick 8 per marketplace spanning the three categories (≥2 face, ≥2 hair, ≥2 body). Commit the config change before running.

- [ ] **Step 3: Dry-run Shopify only to validate the pipeline**

```
cd spike
uv run python scripts/run_sample_crawl.py --dry
```
Expected: 5 retailers × 8 samples = 40 JSON files under `data/parsed/`. No proxy activity. Inspect one:
```
uv run python -c "
import json, pathlib
p = next(pathlib.Path('data/parsed/minimalist').glob('*.json'))
print(json.dumps(json.loads(p.read_text()), indent=2)[:800])
"
```
Expected: a well-formed ParsedSample with non-empty `variants`, `current_price`, etc.

- [ ] **Step 4: Full crawl with proxy**

Preconditions: `.env` populated with real proxy creds; legal review completed (spec §14 open question) or explicit OK from Sasank to proceed for research-only.

```
uv run python scripts/run_sample_crawl.py
```
Expected: ~80 JSON files across `data/parsed/<retailer>/`. Some marketplace fetches will fail (captcha, 503) — that's data: those URLs land as `ParsedSample` with most fields in `missing_fields`. That is *meaningful* for the scorecard — it quantifies the anti-bot problem.

- [ ] **Step 5: Commit the captured data summary (not raw data — gitignored)**

```
git add spike/scripts/run_sample_crawl.py spike/src/spike/config.py
git commit -m "spike: crawl driver + curator-picked marketplace URLs"
```

---

## Task 6: Field-presence scorecard

**Files:**
- Create: `spike/src/spike/scorecard/__init__.py`
- Create: `spike/src/spike/scorecard/analyze.py`
- Create: `spike/src/spike/scorecard/render.py`
- Create: `spike/tests/test_scorecard_analyze.py`
- Create: `spike/tests/test_scorecard_render.py`

- [ ] **Step 1: Write `scorecard/__init__.py`**

```python
```

- [ ] **Step 2: Write failing test `tests/test_scorecard_analyze.py`**

```python
from __future__ import annotations

from spike.models import ParsedSample, Variant
from spike.scorecard.analyze import build_field_matrix, quality_tier


def _sample(retailer: str, **overrides) -> ParsedSample:
    defaults = dict(
        retailer_slug=retailer,
        source_url="https://x/y",
        raw_capture_id="cid",
        canonical_name="N",
        brand_name="B",
        current_price=100.0,
        current_price_raw="100",
        variants=[Variant(option_value="30ml", price=100.0)],
        ingredients_raw="water, glycerin",
        ingredients_source="text",
        description_raw="d",
        images=["http://img"],
        rating_raw="4.5 (10)",
        offers_raw=["offer A"],
        stock_status_raw="in_stock",
        missing_fields=set(),
    )
    defaults.update(overrides)
    return ParsedSample(**defaults)


def test_field_matrix_counts_presence_by_retailer() -> None:
    samples = [
        _sample("minimalist"),
        _sample("minimalist", ingredients_raw=None, missing_fields={"ingredients"}),
        _sample("nykaa"),
        _sample("nykaa", current_price=None, current_price_raw=None,
                missing_fields={"current_price"}),
    ]
    matrix = build_field_matrix(samples)
    ing_mini = next(r for r in matrix
                    if r.field_name == "ingredients" and r.retailer_slug == "minimalist")
    assert ing_mini.present_count == 1
    assert ing_mini.sample_count == 2

    price_nykaa = next(r for r in matrix
                       if r.field_name == "current_price" and r.retailer_slug == "nykaa")
    assert price_nykaa.present_count == 1
    assert price_nykaa.sample_count == 2


def test_quality_tier_classification() -> None:
    assert quality_tier(0.95) == "reliable"
    assert quality_tier(0.70) == "partial"
    assert quality_tier(0.20) == "unreliable"
    assert quality_tier(0.0) == "absent"
```

- [ ] **Step 3: Run test — expect fail**

```
uv run pytest tests/test_scorecard_analyze.py -v
```
Expected: `ModuleNotFoundError: No module named 'spike.scorecard.analyze'`.

- [ ] **Step 4: Write `src/spike/scorecard/analyze.py`**

```python
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from spike.models import FieldPresence, ParsedSample

TRACKED_FIELDS: tuple[str, ...] = (
    "canonical_name",
    "brand_name",
    "category_hint",
    "current_price",
    "compare_at_price",
    "stock_status",
    "variants",
    "ingredients",
    "description",
    "images",
    "rating",
    "offers",
)

QualityTier = Literal["reliable", "partial", "unreliable", "absent"]


def _field_is_present(sample: ParsedSample, field: str) -> bool:
    if field in sample.missing_fields:
        return False
    match field:
        case "canonical_name": return sample.canonical_name is not None
        case "brand_name": return sample.brand_name is not None
        case "category_hint": return sample.category_hint is not None
        case "current_price": return sample.current_price is not None
        case "compare_at_price": return sample.compare_at_price is not None
        case "stock_status": return sample.stock_status_raw is not None
        case "variants": return len(sample.variants) > 0
        case "ingredients": return sample.ingredients_raw is not None
        case "description": return sample.description_raw is not None
        case "images": return len(sample.images) > 0
        case "rating": return sample.rating_raw is not None
        case "offers": return len(sample.offers_raw) > 0
    return False


def build_field_matrix(samples: list[ParsedSample]) -> list[FieldPresence]:
    counts: dict[tuple[str, str], tuple[int, int]] = defaultdict(lambda: (0, 0))
    for s in samples:
        for f in TRACKED_FIELDS:
            present, total = counts[(f, s.retailer_slug)]
            present += 1 if _field_is_present(s, f) else 0
            total += 1
            counts[(f, s.retailer_slug)] = (present, total)
    return [
        FieldPresence(field_name=f, retailer_slug=r, present_count=p, sample_count=t)
        for (f, r), (p, t) in sorted(counts.items())
    ]


def quality_tier(ratio: float) -> QualityTier:
    if ratio >= 0.90: return "reliable"
    if ratio >= 0.50: return "partial"
    if ratio > 0.0: return "unreliable"
    return "absent"
```

- [ ] **Step 5: Run test — expect pass**

```
uv run pytest tests/test_scorecard_analyze.py -v
```
Expected: both tests pass.

- [ ] **Step 6: Write failing test `tests/test_scorecard_render.py`**

```python
from __future__ import annotations

from pathlib import Path

from spike.models import FieldPresence
from spike.scorecard.render import render_csv_matrix, render_scorecard_md


def test_render_csv_contains_header_and_rows(tmp_path: Path) -> None:
    rows = [
        FieldPresence(field_name="current_price", retailer_slug="nykaa",
                      present_count=7, sample_count=8),
        FieldPresence(field_name="ingredients", retailer_slug="nykaa",
                      present_count=2, sample_count=8),
    ]
    out = tmp_path / "matrix.csv"
    render_csv_matrix(rows, out)
    lines = out.read_text().splitlines()
    assert lines[0] == "field,retailer,present,sample_count,presence_ratio"
    assert any("ingredients,nykaa,2,8,0.25" in ln for ln in lines)


def test_render_scorecard_md_groups_by_field(tmp_path: Path) -> None:
    rows = [
        FieldPresence(field_name="current_price", retailer_slug="nykaa",
                      present_count=8, sample_count=8),
        FieldPresence(field_name="current_price", retailer_slug="minimalist",
                      present_count=8, sample_count=8),
        FieldPresence(field_name="ingredients", retailer_slug="nykaa",
                      present_count=2, sample_count=8),
        FieldPresence(field_name="ingredients", retailer_slug="minimalist",
                      present_count=0, sample_count=8),
    ]
    out = tmp_path / "scorecard.md"
    render_scorecard_md(rows, out)
    text = out.read_text()
    assert "## current_price" in text
    assert "## ingredients" in text
    assert "reliable" in text
    assert "absent" in text or "unreliable" in text
```

- [ ] **Step 7: Run test — expect fail**

```
uv run pytest tests/test_scorecard_render.py -v
```
Expected: `ModuleNotFoundError: No module named 'spike.scorecard.render'`.

- [ ] **Step 8: Write `src/spike/scorecard/render.py`**

```python
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from spike.models import FieldPresence
from spike.scorecard.analyze import quality_tier


def render_csv_matrix(rows: list[FieldPresence], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["field", "retailer", "present", "sample_count", "presence_ratio"])
        for r in rows:
            w.writerow([
                r.field_name, r.retailer_slug, r.present_count,
                r.sample_count, f"{r.presence_ratio:.2f}",
            ])


def render_scorecard_md(rows: list[FieldPresence], out: Path) -> None:
    by_field: dict[str, list[FieldPresence]] = defaultdict(list)
    for r in rows:
        by_field[r.field_name].append(r)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# Field-Quality Scorecard", ""]
    for field in sorted(by_field):
        lines.append(f"## {field}")
        lines.append("")
        lines.append("| Retailer | Present | Samples | Ratio | Tier |")
        lines.append("|---|---:|---:|---:|---|")
        for r in sorted(by_field[field], key=lambda x: -x.presence_ratio):
            lines.append(
                f"| {r.retailer_slug} | {r.present_count} | {r.sample_count} | "
                f"{r.presence_ratio:.2f} | {quality_tier(r.presence_ratio)} |"
            )
        lines.append("")
    out.write_text("\n".join(lines))
```

- [ ] **Step 9: Run tests — expect pass**

```
uv run pytest tests/test_scorecard_render.py -v
```
Expected: both tests pass.

- [ ] **Step 10: Wire the reports script `scripts/build_reports.py`**

```python
"""Read all ParsedSamples in data/parsed/*/*.json and emit the reports."""
from __future__ import annotations

import json
from pathlib import Path

from spike.models import ParsedSample
from spike.scorecard.analyze import build_field_matrix
from spike.scorecard.render import render_csv_matrix, render_scorecard_md

SPIKE_ROOT = Path(__file__).resolve().parent.parent


def load_samples() -> list[ParsedSample]:
    parsed_dir = SPIKE_ROOT / "data" / "parsed"
    samples: list[ParsedSample] = []
    for p in parsed_dir.glob("*/*.json"):
        samples.append(ParsedSample.model_validate_json(p.read_text()))
    return samples


def main() -> None:
    samples = load_samples()
    if not samples:
        raise SystemExit("No samples found. Run scripts/run_sample_crawl.py first.")
    matrix = build_field_matrix(samples)
    reports = SPIKE_ROOT / "data" / "reports"
    render_csv_matrix(matrix, reports / "field-matrix.csv")
    render_scorecard_md(matrix, reports / "scorecard.md")
    print(f"Wrote {reports/'field-matrix.csv'} and {reports/'scorecard.md'} "
          f"({len(samples)} samples across {len({s.retailer_slug for s in samples})} retailers)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 11: Run reports against the real crawl output**

```
uv run python scripts/build_reports.py
```
Expected: prints the summary and produces `data/reports/field-matrix.csv` + `data/reports/scorecard.md`. Open the scorecard — this is the primary empirical artifact the spike exists to produce.

- [ ] **Step 12: Commit**

```
git add spike/src/spike/scorecard/ spike/scripts/build_reports.py \
        spike/tests/test_scorecard_analyze.py spike/tests/test_scorecard_render.py
git commit -m "spike: field-matrix + quality-scorecard pipeline"
```

---

## Task 7: v0 schema as baseline + schema-query test harness

**Files:**
- Create: `spike/src/spike/schema/__init__.py`
- Create: `spike/src/spike/schema/v0.sql`
- Create: `spike/tests/test_schema_queries.py`

> **Why load v0 first?** We want a test harness that can run the three canonical queries (price compare, shelf read, search) against whichever schema is active. Loading v0 first validates the harness itself against an unchanged baseline before we edit the schema in Task 8.

- [ ] **Step 1: Write `schema/__init__.py`**

```python
```

- [ ] **Step 2: Write `schema/v0.sql`** (transcribed from spec §8 entities, minimum to run queries)

```sql
-- v0: baseline schema copied from design spec §8. Not authoritative — Task 8 evolves this into v1.
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS users;

CREATE TABLE core.brands (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  own_site TEXT
);

CREATE TABLE core.retailers (
  id BIGSERIAL PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL
);

CREATE TABLE core.products (
  id BIGSERIAL PRIMARY KEY,
  brand_id BIGINT NOT NULL REFERENCES core.brands(id),
  canonical_name TEXT NOT NULL,
  category TEXT,
  subcategory TEXT,
  variants JSONB NOT NULL DEFAULT '[]'::jsonb,
  images JSONB NOT NULL DEFAULT '[]'::jsonb,
  description_raw TEXT,
  description_summary TEXT,
  source_of_truth_retailer_id BIGINT REFERENCES core.retailers(id),
  data_freshness JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX products_name_trgm ON core.products USING gin (canonical_name gin_trgm_ops);
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE core.retailer_listings (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES core.products(id),
  retailer_id BIGINT NOT NULL REFERENCES core.retailers(id),
  listing_url TEXT NOT NULL,
  current_price NUMERIC(10,2),
  compare_at_price NUMERIC(10,2),
  stock_status TEXT,
  current_offers JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_scraped_at TIMESTAMPTZ,
  scraping_confidence NUMERIC(3,2),
  UNIQUE (product_id, retailer_id)
);

CREATE TABLE core.raw_scrapes (
  id BIGSERIAL PRIMARY KEY,
  listing_id BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  scraped_at TIMESTAMPTZ NOT NULL,
  raw_body TEXT NOT NULL,
  raw_price_string TEXT,
  raw_ingredients_text TEXT,
  raw_description TEXT,
  raw_offers_text TEXT,
  fetcher_version TEXT NOT NULL,
  tier_used TEXT NOT NULL
);

CREATE TABLE core.derived_data (
  raw_scrape_id BIGINT PRIMARY KEY REFERENCES core.raw_scrapes(id),
  normalized_price NUMERIC(10,2),
  parsed_ingredients JSONB,
  summary_description TEXT,
  extraction_model_v TEXT,
  confidence_score NUMERIC(3,2)
);

CREATE TABLE users.users (
  id BIGSERIAL PRIMARY KEY,
  phone TEXT UNIQUE,
  email TEXT,
  name TEXT,
  profile JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users.shelf_items (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users.users(id),
  product_id BIGINT NOT NULL REFERENCES core.products(id),
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  purchased_from_retailer_id BIGINT REFERENCES core.retailers(id),
  purchase_price NUMERIC(10,2),
  opened_date DATE,
  pct_remaining INTEGER,
  user_rating NUMERIC(2,1),
  notes TEXT,
  UNIQUE (user_id, product_id)
);
```

- [ ] **Step 3: Write the failing test `tests/test_schema_queries.py`**

```python
from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wand:wand@localhost:5433/wand_spike")
SPIKE_ROOT = Path(__file__).resolve().parent.parent


def _pg_conn():
    # Accept both SQLAlchemy-style and plain DSNs.
    dsn = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(dsn)


def _load_schema(conn: psycopg.Connection, sql_path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS core CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS users CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS scraping CASCADE")
        cur.execute(sql_path.read_text())
    conn.commit()


@pytest.fixture()
def db_v0():
    with _pg_conn() as conn:
        _load_schema(conn, SPIKE_ROOT / "src" / "spike" / "schema" / "v0.sql")
        yield conn


def test_v0_loads_cleanly(db_v0: psycopg.Connection) -> None:
    with db_v0.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.products")
        assert cur.fetchone()[0] == 0


def test_v0_price_compare_query(db_v0: psycopg.Connection) -> None:
    """Cross-retailer minimum-price query — one of Phase 1's core reads."""
    with db_v0.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('Minimalist') RETURNING id")
        brand_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, 'Niacinamide 10%%') RETURNING id",
            (brand_id,),
        )
        product_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailers (slug, name, base_url) VALUES ('minimalist', 'Minimalist', 'https://x'), ('nykaa', 'Nykaa', 'https://y') RETURNING id"
        )
        for (retailer_id,), price in zip(cur.fetchall(), [449.0, 499.0]):
            cur.execute(
                "INSERT INTO core.retailer_listings (product_id, retailer_id, listing_url, current_price) VALUES (%s, %s, %s, %s)",
                (product_id, retailer_id, "https://z", price),
            )

        cur.execute(
            """
            SELECT min(current_price) FROM core.retailer_listings
             WHERE product_id = %s AND current_price IS NOT NULL
            """,
            (product_id,),
        )
        assert cur.fetchone()[0] == 449.0
    db_v0.commit()


def test_v0_shelf_read_query(db_v0: psycopg.Connection) -> None:
    with db_v0.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('Plum') RETURNING id")
        brand_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, 'Vitamin C Serum') RETURNING id",
            (brand_id,),
        )
        product_id = cur.fetchone()[0]
        cur.execute("INSERT INTO users.users (phone) VALUES ('+91-9999999999') RETURNING id")
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO users.shelf_items (user_id, product_id) VALUES (%s, %s)",
            (user_id, product_id),
        )
        cur.execute(
            """
            SELECT p.canonical_name FROM users.shelf_items si
              JOIN core.products p ON p.id = si.product_id
             WHERE si.user_id = %s
            """,
            (user_id,),
        )
        assert [r[0] for r in cur.fetchall()] == ["Vitamin C Serum"]
    db_v0.commit()


def test_v0_search_query_uses_trgm(db_v0: psycopg.Connection) -> None:
    with db_v0.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('The Derma Co') RETURNING id")
        brand_id = cur.fetchone()[0]
        for name in ["1% Kojic Acid Face Serum", "2% Salicylic Face Wash", "Vitamin C Face Moisturizer"]:
            cur.execute(
                "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, %s)",
                (brand_id, name),
            )

        cur.execute(
            "SELECT canonical_name FROM core.products WHERE canonical_name %% 'vitamin c'"
        )
        names = [r[0] for r in cur.fetchall()]
        assert any("Vitamin C" in n for n in names)
    db_v0.commit()
```

- [ ] **Step 4: Start Postgres and run tests**

```
docker compose -f /Users/sdagguba/sasank-playground/docker-compose.yml up -d
cd /Users/sdagguba/sasank-playground/spike
uv run pytest tests/test_schema_queries.py -v
```
Expected: 4 tests pass. `test_v0_loads_cleanly` confirms the schema compiles; the three query tests confirm the critical Phase 1 read paths work.

- [ ] **Step 5: Commit**

```
git add spike/src/spike/schema/__init__.py spike/src/spike/schema/v0.sql \
        spike/tests/test_schema_queries.py
git commit -m "spike: v0 baseline schema + query harness (price compare, shelf, search)"
```

---

## Task 8: Evolve v0 → v1 with evidence from the scorecard

**Files:**
- Create: `spike/src/spike/schema/v1.sql`
- Modify: `spike/tests/test_schema_queries.py` (add v1 fixture + tests)

> **What this task actually is:** the scorecard (Task 6) now contains empirical evidence about which fields are reliable, which are always missing, and which vary across retailers. Translate those findings into v1 SQL deltas. Each non-obvious change has a `-- evidence:` comment citing a scorecard row.

Example evolution guidelines (the engineer fills in specifics from the real scorecard):
- If `ingredients` scorecard for marketplaces < 30% → drop the NOT-NULL assumption nowhere; instead add a `scraping.ingredients_review_queue` table for cases where the agent needs follow-up via vision Tier 4.
- If `compare_at_price` is reliable on Shopify but not marketplaces → keep nullable (matches v0).
- If `stock_status` shape differs across retailers → add `stock_status_raw TEXT` *and* normalized `stock_status` enum (confirms spec §8 decision 5).
- If variant axis count > 1 on even a single retailer → keep JSONB (matches v0 §8 decision 4).
- If `category_hint` from retailer is unreliable (confirmed "Launching" / blank Shopify `product_type` in brainstorm) → mandate the `taxonomy` mapping table introduced in v1.

- [ ] **Step 1: Open the scorecard and list concrete deltas**

Run:
```
less spike/data/reports/scorecard.md
```

As you read, write each concrete delta into a scratch file `spike/schema/v1-changelog.md` in the format:
```
- field: ingredients — evidence: reliable 100% on shopify, <30% on marketplaces — delta: add taxonomy+queue, keep nullable on listings
- field: category_hint — evidence: 50% of Shopify rows blank — delta: introduce taxonomy table + taxonomy_mapping
... etc.
```

Commit this changelog *before* touching v1.sql — it's the trace from evidence → schema decision.

```
git add spike/schema/v1-changelog.md
git commit -m "spike: v1 schema changelog — each delta cites scorecard evidence"
```

- [ ] **Step 2: Write `spike/src/spike/schema/v1.sql`**

Start by copying v0.sql verbatim, then apply each changelog delta with inline evidence comments. Minimum mandatory v1 additions (informed by spec §8 + the expected brainstorm-validated findings):

```sql
-- v1.sql — evolved from v0 based on scorecard evidence. See schema/v1-changelog.md.
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS scraping;
CREATE SCHEMA IF NOT EXISTS taxonomy;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE core.brands (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  logo_url TEXT,
  own_site TEXT
);

CREATE TABLE core.retailers (
  id BIGSERIAL PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  -- evidence: spec §9.6 — marketplaces require proxy/stealth; Shopify does not.
  needs_proxy BOOLEAN NOT NULL DEFAULT FALSE,
  -- evidence: spec §8.2 decision 9 — source-of-truth distinction is retailer-level policy.
  is_authoritative_for_catalog BOOLEAN NOT NULL DEFAULT FALSE
);

-- evidence: scorecard — retailer-supplied product_type is unreliable ("Launching", blank on Shopify).
CREATE TABLE taxonomy.categories (
  id BIGSERIAL PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  parent_id BIGINT REFERENCES taxonomy.categories(id)
);

CREATE TABLE taxonomy.mappings (
  id BIGSERIAL PRIMARY KEY,
  retailer_id BIGINT NOT NULL REFERENCES core.retailers(id),
  retailer_category TEXT NOT NULL,       -- as scraped, verbatim
  category_id BIGINT REFERENCES taxonomy.categories(id),
  confidence NUMERIC(3,2) NOT NULL DEFAULT 0.0,
  source TEXT NOT NULL DEFAULT 'rule',   -- 'rule' | 'llm' | 'human'
  UNIQUE (retailer_id, retailer_category)
);

CREATE TABLE core.products (
  id BIGSERIAL PRIMARY KEY,
  brand_id BIGINT NOT NULL REFERENCES core.brands(id),
  canonical_name TEXT NOT NULL,
  -- evidence: spec §8.2 decision 6 — retailer-provided categories unreliable; canonical ref here.
  canonical_category_id BIGINT REFERENCES taxonomy.categories(id),
  -- evidence: spec §8.2 decision 4 — multi-axis variance confirmed in scorecard (Shopify 100ml/50ml).
  variants JSONB NOT NULL DEFAULT '[]'::jsonb,
  images JSONB NOT NULL DEFAULT '[]'::jsonb,
  description_raw TEXT,
  description_summary TEXT,
  source_of_truth_retailer_id BIGINT REFERENCES core.retailers(id),
  -- evidence: spec §8.2 decision 10 — freshness varies by field (price hourly, ingredients yearly).
  data_freshness JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX products_name_trgm ON core.products USING gin (canonical_name gin_trgm_ops);

-- evidence: spec §8.2 decision 8 — ingredients first-class from Phase 1; enables Phase 2 agents.
CREATE TABLE core.ingredients (
  id BIGSERIAL PRIMARY KEY,
  inci_name TEXT NOT NULL UNIQUE,
  common_name TEXT,
  ingredient_category TEXT,
  concern_tags TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE core.product_ingredients (
  product_id BIGINT NOT NULL REFERENCES core.products(id),
  ingredient_id BIGINT NOT NULL REFERENCES core.ingredients(id),
  position INTEGER,                          -- order on label (1 = first)
  concentration TEXT,                        -- rarely disclosed; keep string
  PRIMARY KEY (product_id, ingredient_id)
);

CREATE TYPE core.stock_status_enum AS ENUM (
  'in_stock', 'low_stock', 'out_of_stock', 'discontinued', 'unknown'
);

CREATE TABLE core.retailer_listings (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES core.products(id),
  retailer_id BIGINT NOT NULL REFERENCES core.retailers(id),
  listing_url TEXT NOT NULL,
  current_price NUMERIC(10,2),
  compare_at_price NUMERIC(10,2),
  -- evidence: spec §8.2 decision 5 — normalized enum + raw string both required.
  stock_status core.stock_status_enum NOT NULL DEFAULT 'unknown',
  stock_status_raw TEXT,
  current_offers JSONB NOT NULL DEFAULT '[]'::jsonb,
  rating_value NUMERIC(3,2),
  rating_count INTEGER,
  last_scraped_at TIMESTAMPTZ,
  scraping_confidence NUMERIC(3,2),
  -- evidence: spec §8.2 decision 1 — cross-retailer aggregation; uniqueness enforced here.
  UNIQUE (product_id, retailer_id)
);

-- evidence: spec §8.2 decision 2 — raw + derived split.
CREATE TABLE core.raw_scrapes (
  id BIGSERIAL PRIMARY KEY,
  listing_id BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  scraped_at TIMESTAMPTZ NOT NULL,
  content_type TEXT NOT NULL,
  body_ref TEXT,                 -- R2/S3 pointer when body > 256KB, else NULL
  body TEXT,                     -- inline when small
  raw_price_string TEXT,
  raw_ingredients_text TEXT,
  raw_description TEXT,
  raw_offers_text TEXT,
  http_status INTEGER,
  fetcher_version TEXT NOT NULL,
  tier_used TEXT NOT NULL
);
CREATE INDEX raw_scrapes_listing_scraped_at ON core.raw_scrapes (listing_id, scraped_at DESC);

CREATE TABLE core.derived_data (
  raw_scrape_id BIGINT PRIMARY KEY REFERENCES core.raw_scrapes(id),
  normalized_price NUMERIC(10,2),
  parsed_ingredients JSONB,
  summary_description TEXT,
  extraction_model_v TEXT,
  confidence_score NUMERIC(3,2)
);

-- evidence: spec §13 — success criterion requires price history partitioning for hourly reads.
CREATE TABLE core.price_history (
  listing_id BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  captured_at TIMESTAMPTZ NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  PRIMARY KEY (listing_id, captured_at)
) PARTITION BY RANGE (captured_at);

-- One initial partition; Sprint 1+ will automate rollover (pg_partman or cron).
CREATE TABLE core.price_history_2026_04 PARTITION OF core.price_history
  FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE core.price_history_2026_05 PARTITION OF core.price_history
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE users.users (
  id BIGSERIAL PRIMARY KEY,
  phone TEXT UNIQUE,
  email TEXT,
  name TEXT,
  -- evidence: spec §8.2 decision 7 — JSONB until a field proves load-bearing.
  profile JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- evidence: spec §5.1 onboarding — theme stored on user, applied app-wide.
  theme_slug TEXT NOT NULL DEFAULT 'tile',
  -- evidence: spec §5.1 step 3 — agent selections persist in Phase 1 for Phase 2 activation.
  selected_agent_slugs TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users.shelf_items (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users.users(id),
  -- evidence: spec §8.2 decision 3 — shelf refs canonical product, not listing.
  product_id BIGINT NOT NULL REFERENCES core.products(id),
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  purchased_from_retailer_id BIGINT REFERENCES core.retailers(id),
  purchase_price NUMERIC(10,2),
  opened_date DATE,
  pct_remaining INTEGER CHECK (pct_remaining BETWEEN 0 AND 100),
  user_rating NUMERIC(2,1) CHECK (user_rating BETWEEN 0 AND 5),
  notes TEXT,
  UNIQUE (user_id, product_id)
);

-- Scraping operational tables — see spec §9.4 for semantics.
CREATE TABLE scraping.scraper_configs (
  id BIGSERIAL PRIMARY KEY,
  retailer_id BIGINT NOT NULL REFERENCES core.retailers(id),
  field_name TEXT NOT NULL,
  selector TEXT NOT NULL,
  selector_kind TEXT NOT NULL,         -- 'css' | 'xpath' | 'jsonld' | 'regex'
  deployed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deployed_by TEXT NOT NULL,           -- 'auto-heal' | 'human:<email>' | 'bootstrap'
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (retailer_id, field_name, is_active) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE scraping.repair_queue (
  id BIGSERIAL PRIMARY KEY,
  listing_id BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  field_name TEXT NOT NULL,
  reason TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  -- evidence: spec §9.4 — cap repairs per URL before escalating to humans.
  max_attempts INTEGER NOT NULL DEFAULT 3,
  llm_cost_inr NUMERIC(10,2) NOT NULL DEFAULT 0.0,
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'healed' | 'escalated'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scraping.human_review_queue (
  id BIGSERIAL PRIMARY KEY,
  listing_id BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  field_name TEXT NOT NULL,
  reason TEXT NOT NULL,
  -- evidence: spec §9.4 — human sees last-known-good selector + what agent tried.
  last_good_config_id BIGINT REFERENCES scraping.scraper_configs(id),
  failed_attempts JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'open',     -- 'open' | 'fixed' | 'unreliable'
  assigned_to TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 3: Extend `tests/test_schema_queries.py` with a `db_v1` fixture and the same three query tests targeting v1**

Append to `tests/test_schema_queries.py`:

```python
@pytest.fixture()
def db_v1():
    with _pg_conn() as conn:
        _load_schema(conn, SPIKE_ROOT / "src" / "spike" / "schema" / "v1.sql")
        yield conn


def test_v1_loads_cleanly(db_v1: psycopg.Connection) -> None:
    with db_v1.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.products")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM scraping.human_review_queue")
        assert cur.fetchone()[0] == 0


def test_v1_stock_status_enum_roundtrip(db_v1: psycopg.Connection) -> None:
    with db_v1.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('Plum') RETURNING id")
        bid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, 'P') RETURNING id",
            (bid,),
        )
        pid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailers (slug, name, base_url) VALUES ('x', 'X', 'https://x') RETURNING id"
        )
        rid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailer_listings (product_id, retailer_id, listing_url, stock_status, stock_status_raw) "
            "VALUES (%s, %s, 'https://y', 'low_stock', 'Only 2 left!') RETURNING stock_status, stock_status_raw",
            (pid, rid),
        )
        status, raw = cur.fetchone()
        assert status == "low_stock"
        assert raw == "Only 2 left!"
    db_v1.commit()


def test_v1_price_history_partition_accepts_insert(db_v1: psycopg.Connection) -> None:
    with db_v1.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('M') RETURNING id")
        bid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, 'Niacinamide') RETURNING id",
            (bid,),
        )
        pid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailers (slug, name, base_url) VALUES ('m', 'M', 'https://m') RETURNING id"
        )
        rid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailer_listings (product_id, retailer_id, listing_url) "
            "VALUES (%s, %s, 'https://m/p') RETURNING id",
            (pid, rid),
        )
        lid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.price_history (listing_id, captured_at, price) "
            "VALUES (%s, '2026-04-17 12:00+00', 449.00)",
            (lid,),
        )
        cur.execute(
            "SELECT price FROM core.price_history WHERE listing_id = %s",
            (lid,),
        )
        assert cur.fetchone()[0] == 449.00
    db_v1.commit()
```

- [ ] **Step 4: Run v1 tests — expect pass**

```
uv run pytest tests/test_schema_queries.py -v
```
Expected: all tests (v0 + v1) pass. If v1 fails, iterate on the SQL until it does — that's the whole point of the spike.

- [ ] **Step 5: Commit**

```
git add spike/src/spike/schema/v1.sql spike/tests/test_schema_queries.py
git commit -m "spike: v1 schema with evidence-cited deltas from scorecard"
```

---

## Task 9: Seed v1 with real parsed samples + verify end-to-end query shape

**Files:**
- Create: `spike/src/spike/schema/seed.py`
- Create: `spike/scripts/seed_and_verify.py`
- Create: `spike/tests/test_seed.py`

- [ ] **Step 1: Write failing test `tests/test_seed.py`**

```python
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from spike.models import ParsedSample, Variant
from spike.schema.seed import load_samples_into_v1

SPIKE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_v1():
    dsn = "postgresql://wand:wand@localhost:5433/wand_spike"
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS core CASCADE")
            cur.execute("DROP SCHEMA IF EXISTS users CASCADE")
            cur.execute("DROP SCHEMA IF EXISTS scraping CASCADE")
            cur.execute("DROP SCHEMA IF EXISTS taxonomy CASCADE")
            cur.execute((SPIKE_ROOT / "src" / "spike" / "schema" / "v1.sql").read_text())
        conn.commit()
        yield conn


def test_seed_creates_products_and_listings(db_v1: psycopg.Connection) -> None:
    samples = [
        ParsedSample(
            retailer_slug="minimalist",
            source_url="https://beminimalist.co/products/niacinamide",
            raw_capture_id="cap-1",
            canonical_name="Niacinamide 10% Serum",
            brand_name="Minimalist",
            category_hint="Serum",
            current_price=449.0,
            current_price_raw="449.00",
            compare_at_price=549.0,
            stock_status_raw="in_stock",
            variants=[Variant(option_value="30ml", price=449.0)],
            description_raw="Balances oil.",
            images=["https://cdn/niacinamide.jpg"],
            missing_fields={"ingredients", "rating"},
        ),
        ParsedSample(
            retailer_slug="nykaa",
            source_url="https://www.nykaa.com/niacinamide",
            raw_capture_id="cap-2",
            canonical_name="Niacinamide 10% Serum",
            brand_name="Minimalist",
            current_price=499.0,
            current_price_raw="499",
            stock_status_raw="InStock",
            rating_raw="4.3 (212)",
            offers_raw=["Flat 10% on Nykaa Prepaid"],
            missing_fields={"ingredients", "category_hint", "compare_at_price", "variants"},
        ),
    ]

    load_samples_into_v1(db_v1, samples)

    with db_v1.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.products")
        assert cur.fetchone()[0] == 1   # dedup across retailers on (brand, canonical_name)
        cur.execute("SELECT count(*) FROM core.retailer_listings")
        assert cur.fetchone()[0] == 2
        cur.execute(
            "SELECT min(current_price) FROM core.retailer_listings "
            "WHERE product_id = (SELECT id FROM core.products LIMIT 1)"
        )
        assert cur.fetchone()[0] == 449.0
```

- [ ] **Step 2: Run test — expect fail**

```
uv run pytest tests/test_seed.py -v
```
Expected: `ModuleNotFoundError: No module named 'spike.schema.seed'`.

- [ ] **Step 3: Write `src/spike/schema/seed.py`**

```python
from __future__ import annotations

from collections import defaultdict

import psycopg

from spike.models import ParsedSample

_STOCK_MAP = {
    "in_stock": "in_stock",
    "InStock": "in_stock",
    "low_stock": "low_stock",
    "LowStock": "low_stock",
    "out_of_stock": "out_of_stock",
    "OutOfStock": "out_of_stock",
    "discontinued": "discontinued",
    "Discontinued": "discontinued",
}


def _normalize_stock(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    return _STOCK_MAP.get(raw, "unknown")


def load_samples_into_v1(conn: psycopg.Connection, samples: list[ParsedSample]) -> None:
    """Idempotent-ish seeder. Groups by (brand, canonical_name) to create one product per SKU."""
    grouped: dict[tuple[str | None, str | None], list[ParsedSample]] = defaultdict(list)
    for s in samples:
        grouped[(s.brand_name, s.canonical_name)].append(s)

    with conn.cursor() as cur:
        # Retailers
        for slug in {s.retailer_slug for s in samples}:
            cur.execute(
                "INSERT INTO core.retailers (slug, name, base_url) VALUES (%s, %s, %s) "
                "ON CONFLICT (slug) DO NOTHING",
                (slug, slug, f"https://{slug}.example"),
            )

        # Products + listings
        for (brand, name), group in grouped.items():
            if brand is None or name is None:
                continue
            cur.execute(
                "INSERT INTO core.brands (name) VALUES (%s) "
                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                (brand,),
            )
            brand_id = cur.fetchone()[0]

            variants = [v.model_dump() for v in group[0].variants] if group[0].variants else []
            images = group[0].images or []
            cur.execute(
                "INSERT INTO core.products (brand_id, canonical_name, variants, images, description_raw) "
                "VALUES (%s, %s, %s::jsonb, %s::jsonb, %s) RETURNING id",
                (brand_id, name, _json(variants), _json(images), group[0].description_raw),
            )
            product_id = cur.fetchone()[0]

            for s in group:
                cur.execute(
                    "SELECT id FROM core.retailers WHERE slug = %s", (s.retailer_slug,)
                )
                retailer_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO core.retailer_listings "
                    "(product_id, retailer_id, listing_url, current_price, compare_at_price, "
                    " stock_status, stock_status_raw, current_offers, last_scraped_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, now()) "
                    "ON CONFLICT (product_id, retailer_id) DO UPDATE "
                    "SET current_price = EXCLUDED.current_price, "
                    "    last_scraped_at = EXCLUDED.last_scraped_at",
                    (
                        product_id, retailer_id, s.source_url,
                        s.current_price, s.compare_at_price,
                        _normalize_stock(s.stock_status_raw), s.stock_status_raw,
                        _json(s.offers_raw),
                    ),
                )
    conn.commit()


def _json(value) -> str:
    import json
    return json.dumps(value)
```

- [ ] **Step 4: Run test — expect pass**

```
uv run pytest tests/test_seed.py -v
```
Expected: pass. (Requires Postgres running from Task 7.)

- [ ] **Step 5: Write `scripts/seed_and_verify.py`**

```python
"""Load v1 schema, seed with all parsed samples, run canonical query checks."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from spike.models import ParsedSample
from spike.schema.seed import load_samples_into_v1

SPIKE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SPIKE_ROOT / ".env")

DSN = os.getenv("DATABASE_URL", "postgresql://wand:wand@localhost:5433/wand_spike") \
    .replace("postgresql+psycopg://", "postgresql://")


def _reset_and_load_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for schema in ("core", "users", "scraping", "taxonomy"):
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        cur.execute((SPIKE_ROOT / "src" / "spike" / "schema" / "v1.sql").read_text())
    conn.commit()


def _load_parsed_samples() -> list[ParsedSample]:
    return [
        ParsedSample.model_validate_json(p.read_text())
        for p in (SPIKE_ROOT / "data" / "parsed").glob("*/*.json")
    ]


def main() -> None:
    with psycopg.connect(DSN) as conn:
        _reset_and_load_schema(conn)
        samples = _load_parsed_samples()
        if not samples:
            raise SystemExit("No parsed samples found — run run_sample_crawl.py first")
        load_samples_into_v1(conn, samples)

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM core.products")
            n_products = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM core.retailer_listings")
            n_listings = cur.fetchone()[0]
            cur.execute(
                "SELECT p.canonical_name, min(rl.current_price), count(rl.id) "
                "FROM core.products p JOIN core.retailer_listings rl ON rl.product_id = p.id "
                "WHERE rl.current_price IS NOT NULL "
                "GROUP BY p.id, p.canonical_name ORDER BY count(rl.id) DESC LIMIT 5"
            )
            top = cur.fetchall()

    print(f"Seeded {n_products} products, {n_listings} listings.")
    print("Top products by retailer coverage:")
    for name, price, n in top:
        print(f"  {name!r}: min ₹{price} across {n} retailers")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run end-to-end**

```
uv run python scripts/seed_and_verify.py
```
Expected: non-zero products + listings; top-5 list shows at least 1 product with multi-retailer coverage. If the top list is empty, the dedup by `(brand, canonical_name)` isn't finding cross-retailer matches — that IS a finding to capture in the memo (it means dedup will need LLM tiebreaker in Sprint 2, as spec §9.5 predicts).

- [ ] **Step 7: Commit**

```
git add spike/src/spike/schema/seed.py spike/scripts/seed_and_verify.py spike/tests/test_seed.py
git commit -m "spike: v1 seeder + end-to-end verify script"
```

---

## Task 10: Decision memo

**Files:**
- Create: `spike/memo/decision-memo.md`

- [ ] **Step 1: Write the memo with required sections**

Template (fill from actual scorecard numbers and v1 changelog):

```markdown
# Wand Phase 1 — Schema Validation Spike Decision Memo

**Date:** 2026-04-17 to 2026-04-24
**Author:** <engineer>
**Status:** v1 schema locked; recommend proceeding to Sprint 1 migrations

## 1. What the spike did
Scraped <N> samples across <K> retailers. Built field-quality scorecard. Stress-tested v0 schema. Produced v1 with evidence-cited deltas.

## 2. Top 5 findings (from scorecard)
<Fill: each finding = one sentence of observation + one-sentence implication.>
Examples (template):
- Shopify `/products.json` never exposes ingredients → Tier 3 (LLM) or Tier 4 (vision) required for 100% of D2C ingredient coverage.
- Nykaa / Amazon anti-bot success rate under residential proxy during spike was <X%> → Sprint 2 must budget higher proxy spend or add CAPTCHA solver.
- `product_type` from Shopify blank on <Y%> of samples → canonical taxonomy + mapping table is load-bearing, not optional.
- <more>

## 3. v0 → v1 deltas (evidence map)
<Table: field → scorecard signal → schema change. One row per delta from v1-changelog.md.>

## 4. Queries verified against seeded data
- Cross-retailer min price by product — PASS (example: "<name>" @ ₹<X> across <N> retailers)
- Shelf read by user — PASS
- Trigram name search — PASS (top-3 for "niacinamide": <list>)

## 5. Open risks carried into Sprint 1
- <e.g., dedup fuzzy-match approach; variant-axis normalization across shade-heavy products>
- <e.g., image CDN cost at 15k products with average 3 images each>

## 6. Recommendation
Proceed to Sprint 1 (migrations) using v1. Defer <list> to later sprints with explicit tracking issues.
```

- [ ] **Step 2: Fill each section from real data (requires the scorecard + seed results to already exist)**

Concrete: paste top-line stats from `data/reports/scorecard.md`, copy the v1-changelog entries, paste 3 real query results from Task 9 Step 6.

- [ ] **Step 3: Commit**

```
git add spike/memo/decision-memo.md
git commit -m "spike: decision memo locking v1 schema for sprint 1 handoff"
```

---

## Task 11: Spike wrap-up

**Files:**
- Modify: `spike/README.md`
- Modify: top-level `README.md`

- [ ] **Step 1: Update spike README with end-of-spike state**

Append to `spike/README.md`:

```markdown
## Spike output (end state)

- `data/reports/field-matrix.csv` — field × retailer presence matrix (N samples)
- `data/reports/scorecard.md` — quality tiers per field per retailer
- `src/spike/schema/v1.sql` — authoritative schema for Sprint 1
- `memo/decision-memo.md` — why v1 differs from v0
- `tests/` — reproducible harness (run `uv run pytest`)

## What survives into Sprint 1
Only `schema/v1.sql` + `memo/decision-memo.md` + `data/reports/` get promoted.
Everything else is disposable spike code.

## What the spike did NOT cover (intentional)
- Alembic migrations — Sprint 1
- Redis / Temporal / R2 — Sprint 2
- Any frontend code — Sprint 3+
- Computer-use / agent framework — Phase 2/3
```

- [ ] **Step 2: Update top-level README**

Overwrite `/Users/sdagguba/sasank-playground/README.md` (create if absent) with:

```markdown
# Wand

AI-native skincare aggregator for India Gen Z — skin, hair, body.
See `docs/superpowers/specs/` for design specs and `docs/superpowers/plans/` for implementation plans.

## Current status
- Phase 1 design spec: `docs/superpowers/specs/2026-04-17-wand-phase-1-catalog-shelf-design.md`
- Phase 1 Sprint 0 (Schema Validation Spike): complete — see `spike/memo/decision-memo.md`
- Phase 1 Sprint 1+: plans forthcoming

## Layout
- `spike/` — disposable Sprint 0 workspace (v1 schema lives here until Sprint 1 promotes it)
- `docs/` — specs, plans, memos
```

- [ ] **Step 3: Push**

```
cd /Users/sdagguba/sasank-playground
git push origin main
```

- [ ] **Step 4: Hand off to Sprint 1 planning**

The following artifacts are now the inputs to the Sprint 1 plan:
- `spike/src/spike/schema/v1.sql` — verbatim source for the first Alembic migration
- `spike/memo/decision-memo.md` — risks and follow-ups Sprint 1 must address
- `spike/data/reports/scorecard.md` — ingestion prioritization (start with reliable-field retailers)

Write Sprint 1 plan as `docs/superpowers/plans/YYYY-MM-DD-wand-phase-1-sprint-1-foundation.md`, covering: repo monorepo structure (backend/ + web/), FastAPI skeleton, Alembic setup, v1 migration applied, Next.js skeleton, CI pipeline, dev docker-compose with Postgres+Redis+R2-local (MinIO).

---

## Subsequent Sprints (Roadmap — separate plans to follow)

Each gets its own plan, written at the start of that sprint once the previous sprint's artifacts are in hand.

| Sprint | Goal | Entry criteria | Exit criteria |
|---|---|---|---|
| **Sprint 1 — Foundation** (weeks 2-3) | Monorepo, FastAPI + Next.js skeletons, Alembic with v1 migration applied, CI | v1.sql + memo locked | Postgres has v1 schema; `/health` on API; Next.js renders landing placeholder; CI green on PRs |
| **Sprint 2 — Scraping Tiers 0+1** (weeks 3-5) | Production Shopify ingester + marketplace Tier 1 selector scraper + Temporal workflows + browser pool + proxy config | Sprint 1 exit | 5 Shopify brands fully ingested (catalog+price); 1 marketplace (Nykaa) with 500 SKUs ingested |
| **Sprint 3 — Tiers 2-4 + Self-Healing** (weeks 5-7) | LLM selector repair, Tier 3 LLM extract, Tier 4 vision, repair/human queues, admin UI | Sprint 2 exit | Selector repair demonstrably recovers from induced DOM change; human queue UI functional |
| **Sprint 4 — Catalog Scale-out** (weeks 6-8, parallel with 3) | Dedup agent, ingredient parsing, canonical taxonomy, ingest to 15-20k SKUs across all Tier 1 retailers | Tier 0+1 stable | 15-20k SKUs live; <5% scrape events in human queue |
| **Sprint 5 — Backend API + Auth** (weeks 7-9) | Phone-OTP auth, products/listings/search/shelf/profile endpoints, rate limiting | Catalog populated | Full API surface per spec §6; contract tests green |
| **Sprint 6 — Frontend Core** (weeks 8-11) | Design system, landing, product detail page, search/browse, SSR for SEO | API stable | `/p/<slug>` renders with JSON-LD; Lighthouse mobile ≥90 |
| **Sprint 7 — Onboarding + Shelf** (weeks 10-13) | 4-step onboarding, visual bathroom-shelf UI, themes, agent picker UI | Frontend core shipped | p90 onboarding <90s in manual testing; shelf persists across sessions |
| **Sprint 8 — Price Pipeline + Ops** (weeks 12-15) | Hourly price refresh at scale, partitioned price history, quality agent, alerting, dashboards | Catalog + shelf live | <2% stale price rate; on-call runbook complete |
| **Sprint 9 — Beta Launch** (weeks 15-16) | 100-user private beta, success-criteria validation per spec §13 | All exits cleared | Spec §13 criteria met and documented |

---

## Self-Review (performed inline before handoff)

- **Spec coverage:** every spec §11 activity (sample N products, field matrix, quality scorecard, schema stress points, v1 with evidence, seed and verify, decision memo) maps to Tasks 2–10. ✓
- **Placeholders:** all REPLACE URLs are explicitly flagged as curator-filled with an inline rationale; no "TBD", no "handle edge cases", no stub steps. ✓
- **Type consistency:** `ParsedSample`, `RawCapture`, `Variant`, `FieldPresence` used consistently across samplers, scorecard, and seeder. Method names (`sample`, `build_field_matrix`, `load_samples_into_v1`) stable throughout. ✓
- **Schema references:** v0 schema matches spec §8 entities; v1 additions each trace back either to a spec §8.2 decision or to a scorecard-derived `evidence:` comment. ✓

---

**Plan complete.** Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Uses superpowers:subagent-driven-development.
2. **Inline Execution** — execute tasks in this session using superpowers:executing-plans, batch with checkpoints.

Which approach?
