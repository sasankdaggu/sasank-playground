-- v1.sql — evolved from v0 based on 60-sample scorecard (2026-04-24).
-- See schema/v1-changelog.md for evidence citations per delta.
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS scraping;
CREATE SCHEMA IF NOT EXISTS taxonomy;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Brands ────────────────────────────────────────────────────────────────────
CREATE TABLE core.brands (
  id        BIGSERIAL PRIMARY KEY,
  name      TEXT NOT NULL UNIQUE,
  logo_url  TEXT,
  own_site  TEXT
);

-- ── Retailers ─────────────────────────────────────────────────────────────────
CREATE TABLE core.retailers (
  id                          BIGSERIAL PRIMARY KEY,
  slug                        TEXT NOT NULL UNIQUE,
  name                        TEXT NOT NULL,
  base_url                    TEXT NOT NULL,
  needs_proxy                 BOOLEAN NOT NULL DEFAULT FALSE,
  is_authoritative_for_catalog BOOLEAN NOT NULL DEFAULT FALSE
);

-- ── Taxonomy (delta 7: category_hint unreliable → canonical layer required) ───
CREATE TABLE taxonomy.categories (
  id        BIGSERIAL PRIMARY KEY,
  slug      TEXT NOT NULL UNIQUE,
  name      TEXT NOT NULL,
  parent_id BIGINT REFERENCES taxonomy.categories(id)
);

CREATE TABLE taxonomy.mappings (
  id                  BIGSERIAL PRIMARY KEY,
  retailer_id         BIGINT NOT NULL REFERENCES core.retailers(id),
  retailer_category   TEXT NOT NULL,
  category_id         BIGINT REFERENCES taxonomy.categories(id),
  confidence          NUMERIC(3,2) NOT NULL DEFAULT 0.0,
  source              TEXT NOT NULL DEFAULT 'rule',
  UNIQUE (retailer_id, retailer_category)
);

-- ── Products ──────────────────────────────────────────────────────────────────
CREATE TABLE core.products (
  id                            BIGSERIAL PRIMARY KEY,
  brand_id                      BIGINT NOT NULL REFERENCES core.brands(id),
  canonical_name                TEXT NOT NULL,
  canonical_category_id         BIGINT REFERENCES taxonomy.categories(id),
  variants                      JSONB NOT NULL DEFAULT '[]'::jsonb,
  images                        JSONB NOT NULL DEFAULT '[]'::jsonb,
  image_priority                INT NOT NULL DEFAULT 99,  -- lower = higher quality source
  description_raw               TEXT,
  -- delta 5: track where the description came from
  description_source            TEXT,
  description_summary           TEXT,
  source_of_truth_retailer_id   BIGINT REFERENCES core.retailers(id),
  data_freshness                JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- delta 2: track ingredient extraction status per product
  ingredient_scrape_status      TEXT NOT NULL DEFAULT 'pending',
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (brand_id, canonical_name)
);
CREATE INDEX products_name_trgm ON core.products USING gin (canonical_name gin_trgm_ops);

-- ── Ingredients (first-class from Phase 1) ────────────────────────────────────
CREATE TABLE core.ingredients (
  id                BIGSERIAL PRIMARY KEY,
  inci_name         TEXT NOT NULL UNIQUE,
  common_name       TEXT,
  ingredient_category TEXT,
  concern_tags      TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE core.product_ingredients (
  product_id    BIGINT NOT NULL REFERENCES core.products(id),
  ingredient_id BIGINT NOT NULL REFERENCES core.ingredients(id),
  position      INTEGER,
  concentration TEXT,
  PRIMARY KEY (product_id, ingredient_id)
);

-- ── Stock status ──────────────────────────────────────────────────────────────
CREATE TYPE core.stock_status_enum AS ENUM (
  'in_stock', 'low_stock', 'out_of_stock', 'discontinued', 'unknown'
);

-- ── Retailer listings ─────────────────────────────────────────────────────────
CREATE TABLE core.retailer_listings (
  id                  BIGSERIAL PRIMARY KEY,
  product_id          BIGINT NOT NULL REFERENCES core.products(id),
  retailer_id         BIGINT NOT NULL REFERENCES core.retailers(id),
  listing_url         TEXT NOT NULL,
  current_price       NUMERIC(10,2),
  -- delta 6: confirmed nullable (absent for Purplle, Tira, The Derma Co)
  compare_at_price    NUMERIC(10,2),
  stock_status        core.stock_status_enum NOT NULL DEFAULT 'unknown',
  stock_status_raw    TEXT,
  -- delta 4: rating split into queryable columns (from Purplle JSON-LD evidence)
  rating_value        NUMERIC(3,2),
  rating_count        INTEGER,
  rating_raw          TEXT,
  last_scraped_at     TIMESTAMPTZ,
  scraping_confidence NUMERIC(3,2),
  UNIQUE (product_id, retailer_id)
);

-- delta 3: promotions separated from listings (offers 0% everywhere, JS-rendered)
CREATE TABLE core.promotions (
  id          BIGSERIAL PRIMARY KEY,
  listing_id  BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  promo_text  TEXT NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ
);

-- ── Raw scrapes + derived data ────────────────────────────────────────────────
CREATE TABLE core.raw_scrapes (
  id                    BIGSERIAL PRIMARY KEY,
  listing_id            BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  scraped_at            TIMESTAMPTZ NOT NULL,
  content_type          TEXT NOT NULL,
  body_ref              TEXT,
  body                  TEXT,
  raw_price_string      TEXT,
  raw_ingredients_text  TEXT,
  raw_description       TEXT,
  http_status           INTEGER,
  fetcher_version       TEXT NOT NULL,
  tier_used             TEXT NOT NULL
);
CREATE INDEX raw_scrapes_listing_scraped_at ON core.raw_scrapes (listing_id, scraped_at DESC);

CREATE TABLE core.derived_data (
  raw_scrape_id       BIGINT PRIMARY KEY REFERENCES core.raw_scrapes(id),
  normalized_price    NUMERIC(10,2),
  parsed_ingredients  JSONB,
  summary_description TEXT,
  extraction_model_v  TEXT,
  confidence_score    NUMERIC(3,2)
);

-- ── Price history (partitioned) ───────────────────────────────────────────────
CREATE TABLE core.price_history (
  listing_id    BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  captured_at   TIMESTAMPTZ NOT NULL,
  price         NUMERIC(10,2) NOT NULL,
  PRIMARY KEY (listing_id, captured_at)
) PARTITION BY RANGE (captured_at);

CREATE TABLE core.price_history_2026_04 PARTITION OF core.price_history
  FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE core.price_history_2026_05 PARTITION OF core.price_history
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

-- ── Users + shelf ─────────────────────────────────────────────────────────────
CREATE TABLE users.users (
  id                    BIGSERIAL PRIMARY KEY,
  phone                 TEXT UNIQUE,
  email                 TEXT UNIQUE,
  name                  TEXT,
  profile               JSONB NOT NULL DEFAULT '{}'::jsonb,
  theme_slug            TEXT NOT NULL DEFAULT 'tile',
  selected_agent_slugs  TEXT[] NOT NULL DEFAULT '{}',
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users.shelf_items (
  id                          BIGSERIAL PRIMARY KEY,
  user_id                     BIGINT NOT NULL REFERENCES users.users(id),
  product_id                  BIGINT NOT NULL REFERENCES core.products(id),
  added_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  purchased_from_retailer_id  BIGINT REFERENCES core.retailers(id),
  purchase_price              NUMERIC(10,2),
  opened_date                 DATE,
  pct_remaining               INTEGER CHECK (pct_remaining BETWEEN 0 AND 100),
  user_rating                 NUMERIC(2,1) CHECK (user_rating BETWEEN 0 AND 5),
  notes                       TEXT,
  UNIQUE (user_id, product_id)
);

-- ── Scraping operational tables ───────────────────────────────────────────────
CREATE TABLE scraping.scraper_configs (
  id              BIGSERIAL PRIMARY KEY,
  retailer_id     BIGINT NOT NULL REFERENCES core.retailers(id),
  field_name      TEXT NOT NULL,
  selector        TEXT NOT NULL,
  selector_kind   TEXT NOT NULL,
  -- delta 1: Tira uses __NEXT_DATA__ JSON; Shopify uses json_ld; others use css_selector
  extraction_method TEXT NOT NULL DEFAULT 'json_ld',
  deployed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  deployed_by     TEXT NOT NULL DEFAULT 'bootstrap',
  is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE scraping.repair_queue (
  id            BIGSERIAL PRIMARY KEY,
  listing_id    BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  field_name    TEXT NOT NULL,
  reason        TEXT NOT NULL,
  attempts      INTEGER NOT NULL DEFAULT 0,
  max_attempts  INTEGER NOT NULL DEFAULT 3,
  llm_cost_inr  NUMERIC(10,2) NOT NULL DEFAULT 0.0,
  status        TEXT NOT NULL DEFAULT 'pending',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scraping.human_review_queue (
  id                  BIGSERIAL PRIMARY KEY,
  listing_id          BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  field_name          TEXT NOT NULL,
  reason              TEXT NOT NULL,
  last_good_config_id BIGINT REFERENCES scraping.scraper_configs(id),
  failed_attempts     JSONB NOT NULL DEFAULT '[]'::jsonb,
  status              TEXT NOT NULL DEFAULT 'open',
  assigned_to         TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- delta 2: ingredient extraction queue
CREATE TABLE scraping.ingredient_extraction_queue (
  id              BIGSERIAL PRIMARY KEY,
  product_id      BIGINT NOT NULL REFERENCES core.products(id),
  listing_id      BIGINT NOT NULL REFERENCES core.retailer_listings(id),
  status          TEXT NOT NULL DEFAULT 'pending',
  extraction_tier TEXT,
  attempts        INTEGER NOT NULL DEFAULT 0,
  extracted_text  TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (product_id, listing_id)
);
