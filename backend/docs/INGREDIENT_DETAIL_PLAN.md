# Ingredient Detail Aggregation — Plan

Spike summaries for EWG, INCIDecoder, EU CosIng, COSDNA. Two-layer scraping plan
mirroring the INCI extraction system. All data is stored with citation URLs so we
can prove provenance to users.

## Source Comparison

| Source        | Unique Value                                   | Scrape Difficulty | Robots/ToS Risk |
|---------------|------------------------------------------------|-------------------|-----------------|
| EWG Skin Deep | Hazard 1-10, concerns matrix, data availability| **High** — Cloudflare challenge, Drupal HTML | EULA "non-commercial" — attribute, link out, contact for license |
| INCIDecoder   | Plain-English summary, ID-Rating, irritancy/comedo | **Low** — server-rendered, sitemap available | Permissive robots, no published ToS |
| EU CosIng     | Regulatory truth — Annex restrictions, official function vocab | **Medium** — ColdFusion SPA, JS hydration, no bulk export | Public-sector, broadly reusable with attribution |
| COSDNA        | Acne 0-5, irritant 0-5, plain-English function | **Medium** — server-rendered but blocks AI bots in robots.txt | Disallows AI UAs; use respectful UA + caching, on-demand only |

## Unified Schema

3 tables (migration `0009_ingredient_detail_schema.py`):

1. **`scraping.ingredient_source_strategies`** — Layer 1 registry. Per source:
   `base_url`, `url_template`, `slug_rule`, `requires_js`, `rate_limit_ms`, `status`.
2. **`core.ingredient_detail_sources`** — raw per-source records keyed by
   `(ingredient_id, source)`. Holds normalized fields where present, `raw_payload`
   JSONB for re-parse, `source_url` for citation. Source-specific fields:
   - EWG: `ewg_hazard_low/high`, `ewg_data_avail`, `ewg_concerns` JSONB
   - INCIDecoder: `id_rating`, comedogenicity in `raw_payload`
   - CosIng: `cosing_annex`, `cosing_restriction`
   - COSDNA: `cosdna_acne`, `cosdna_irritant`, `cosdna_safety`
3. **`core.ingredient_detail`** — collated/canonical view per ingredient. Merge
   job picks best-of-source for description, unions `functions` arrays, keeps
   `citation_urls` JSONB so the UI can show "Source: EWG / INCIDecoder / CosIng"
   chips with deep links. `confidence_score` reflects source agreement.

Plus a queue: `scraping.ingredient_detail_queue` (pending / running / done /
failed / not_found / skipped) — same pattern as `ingredient_extraction_queue`.

## Two-Layer Scraping

**Layer 1 — Source detection (one-time per source).**
- Run once per source to populate `ingredient_source_strategies`.
- Determines URL template, JS requirement, rate limits, anti-bot posture.
- Manual or scripted spike (this spike already covers the 4 sources).

**Layer 2 — Per-(ingredient × source) extraction (per ingredient).**
- For each row in `core.ingredients`, enqueue one job per `active` source.
- Worker pulls a job, resolves the URL via `slug_rule`, fetches, extracts
  normalized fields, writes a row to `core.ingredient_detail_sources`.
- Each job hits one source so retries/backoffs are isolated.
- After all sources for an ingredient are done (or N attempts), a merge step
  populates `core.ingredient_detail`.

Mirrors INCI extraction pattern: `ingredient_strategies` ↔ `ingredient_source_strategies`,
`ingredient_extraction_queue` ↔ `ingredient_detail_queue`.

## Slug / URL Resolution Rules

| Source        | Rule                                                                   |
|---------------|------------------------------------------------------------------------|
| INCIDecoder   | `slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')`. URL `https://incidecoder.com/ingredients/{slug}`. Fallback: sitemap-ingredients.0.xml lookup. |
| EWG           | URL needs numeric ID + uppercased slug. No public mapping; resolve via Brave/DDG `site:ewg.org/skindeep/ingredients` query, then store `(ewg_id, slug)`. URL `https://www.ewg.org/skindeep/ingredients/{id}-{SLUG_UPPER}/`. |
| CosIng        | Search by INCI name → 302 to `https://ec.europa.eu/growth/tools-databases/cosing/details/{cosing_id}`. Cache `(name → cosing_id)` after first hit. |
| COSDNA        | `https://www.cosdna.com/eng/stuff.php?q={name}` → 302 → `https://www.cosdna.com/eng/{hex_id}.html`. Cache `(name → hex_id)`. |

## Anti-Bot / Rate-Limit Plan

| Source        | Approach                                                              |
|---------------|-----------------------------------------------------------------------|
| INCIDecoder   | `httpx` + UA "Wand-Bot/0.1 (contact: …)"; 1 req/s; cache 30 days.    |
| EWG           | Playwright stealth via Smartproxy residential; 1 req/2s; back off 403. Persist Cloudflare clearance cookie. |
| CosIng        | Playwright OR reverse-engineered XHR; 1 req/3s.                       |
| COSDNA        | `httpx` + browser-like UA (NOT AI bot UA); 1 req/2s; on-demand only — do not bulk-crawl. |

## Phased Rollout

**P0 — INCIDecoder (lowest risk, highest immediate value).**
Cover all unique ingredients we currently extract (~700 products → ~1.5k unique INCI). Build the worker, prove the merge pipeline.

**P1 — EU CosIng.** Adds regulatory layer (annex restrictions, official functions).
Higher engineering cost (Playwright). Run quarterly cadence.

**P2 — EWG Skin Deep.** Highest user value (hazard + concerns matrix), highest risk.
Requires Cloudflare-bypass infrastructure + license conversation with EWG before public launch. Treat output as license-aware: store `ewg_url` always; only cache score; link out for full detail.

**P3 — COSDNA.** On-demand fetch only (acne / irritant fill-in for ingredients
that lack a comedogenicity score from other sources). No bulk crawl.

## Citation Surface

Every ingredient detail page in Wand UI shows:

> Sources: [EWG ↗] [INCIDecoder ↗] [EU CosIng ↗] [COSDNA ↗]

with each link going to the canonical source URL stored in
`core.ingredient_detail.citation_urls`. Confidence indicator (e.g.
`3 of 4 sources agree`) drives a small badge.

## Health Monitoring

Already wired into the dashboard via `scraper_kind='ingredient_detail'`,
`scraper_target` ∈ {`ewg`, `incidecoder`, `cosing`, `cosdna`}. Each Layer 2 worker run
calls `record_run()` so per-source uptime is visible.
