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

CREATE EXTENSION IF NOT EXISTS pg_trgm;

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
