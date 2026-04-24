# Wand Schema Validation Spike

**Status:** Complete  
**Goal:** Produce an empirically validated v1 schema + field-quality scorecard from real product data.  
**Spec:** `docs/superpowers/specs/2026-04-17-wand-phase-1-catalog-shelf-design.md`  
**Plan:** `docs/superpowers/plans/2026-04-17-wand-phase-1-sprint-0-schema-validation-spike.md`

## What was built

- `src/spike/config.py` — retailer registry (5 Shopify D2C + 4 marketplaces)
- `src/spike/models.py` — Pydantic models: RawCapture, ParsedSample, FieldPresence
- `src/spike/samplers/` — Shopify (Tier 0) + Marketplace (Playwright + JSON-LD) samplers
- `src/spike/scorecard/` — field-matrix builder + CSV/Markdown renderer
- `src/spike/schema/v0.sql` — baseline schema (spec §8)
- `src/spike/schema/v1.sql` — evolved schema with scorecard evidence
- `src/spike/schema/v1-changelog.md` — 8 deltas with evidence citations
- `src/spike/schema/seed.py` — seed loader for v1 Postgres
- `scripts/local_browser_scrape.py` — local Playwright scraper (Tira + Purplle, no proxy)
- `scripts/run_sample_crawl.py` — Shopify D2C sampler runner
- `scripts/build_reports.py` — scorecard generator
- `scripts/seed_and_verify.py` — v1 schema load + seed + query verification

## Deliverables

| File | Description |
|------|-------------|
| `data/reports/field-matrix.csv` | Field × retailer presence matrix (60 samples, 7 retailers) |
| `data/reports/scorecard.md` | Field-quality scorecard with reliability tiers |
| `src/spike/schema/v1.sql` | Production-ready v1 schema for Sprint 1 migrations |
| `src/spike/schema/v1-changelog.md` | Evidence-backed changelog for each schema delta |
| `memo/decision-memo.md` | 5-page decision memo: findings, deltas, Sprint 1 implications |

## Key findings (face skincare, 60 samples)

- **Ingredients: 0% everywhere** — never in /products.json or JSON-LD; needs dedicated product-page scrape
- **Tira: all fields absent** — React/Next.js app; data in `__NEXT_DATA__` JSON, not HTML
- **Nykaa + Amazon.in: blocked** — residential proxy required for hardened marketplaces
- **Offers: 0% everywhere** — JS-rendered, separated into `core.promotions` table in v1
- **Rating: only Purplle (90%)** — split into `rating_value` + `rating_count` columns in v1

## Running the spike

### Prerequisites
```
cp .env.example .env    # fill in DATABASE_URL if you have Postgres
```

### Collect data (already done — data/parsed/ exists)
```
# Shopify D2C brands (no proxy):
python scripts/run_sample_crawl.py --dry

# Tira + Purplle (local browser, no proxy):
python scripts/local_browser_scrape.py
```

### Generate scorecard
```
python scripts/build_reports.py
```

### Seed v1 schema (requires Docker)
```
docker compose -f ../docker-compose.yml up -d
python scripts/seed_and_verify.py
```

### Run tests
```
pytest                              # unit tests (no Postgres needed)
pytest tests/test_schema_queries.py # schema tests (requires Postgres)
```
