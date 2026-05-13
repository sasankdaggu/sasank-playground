"""Add ingredient detail schema: source registry, raw per-source records, collated view

Pattern (mirrors the INCI 2-layer system):
  Layer 1 — scraping.ingredient_source_strategies: which sources to try, URL patterns,
            extraction selectors, status (active/no_data/blocked).
  Layer 2 — core.ingredient_detail_sources: per-source raw fetched payloads keyed by
            (ingredient_id, source). Citations live here.
  Aggregate — core.ingredient_detail: collated/canonical view per ingredient, populated
            from the per-source rows by a merge job. Holds best-of values + provenance.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-25
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Layer 1: per-source strategy (which sources, how to fetch) ----
    op.execute("""
        CREATE TABLE scraping.ingredient_source_strategies (
            id              BIGSERIAL PRIMARY KEY,
            source          TEXT NOT NULL UNIQUE,
                            -- 'ewg' | 'incidecoder' | 'cosing' | 'cosdna'
            base_url        TEXT NOT NULL,
            url_template    TEXT NOT NULL,
                            -- e.g. 'https://incidecoder.com/ingredients/{slug}'
            slug_rule       TEXT NOT NULL,
                            -- 'lower_hyphen' | 'cas_lookup' | 'search_redirect' | 'cosing_id'
            requires_js     BOOLEAN NOT NULL DEFAULT false,
            rate_limit_ms   INT NOT NULL DEFAULT 1500,
            user_agent      TEXT,                       -- override if source bans default
            status          TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','blocked','manual_only','disabled')),
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # ---- Layer 2: per-source raw records keyed by (ingredient, source) ----
    op.execute("""
        CREATE TABLE core.ingredient_detail_sources (
            id              BIGSERIAL PRIMARY KEY,
            ingredient_id   BIGINT NOT NULL REFERENCES core.ingredients(id) ON DELETE CASCADE,
            source          TEXT NOT NULL,
                            -- matches scraping.ingredient_source_strategies.source
            source_url      TEXT NOT NULL,              -- citation URL we show users
            source_id       TEXT,                       -- e.g. cosing numeric id, cosdna hex id
            -- Common normalized fields, NULL if source didn't provide
            inci_name       TEXT,
            cas_number      TEXT,
            ec_number       TEXT,
            iupac_name      TEXT,
            functions       TEXT[],                     -- function tags
            description     TEXT,                       -- plain-English summary
            -- Source-specific scores
            ewg_hazard_low  INT,                        -- 1-10
            ewg_hazard_high INT,
            ewg_data_avail  TEXT,                       -- 'limited'|'fair'|'good'|'robust'|'none'
            ewg_concerns    JSONB,                      -- {cancer:'low', allergy:'high', ...}
            cosdna_acne     INT,                        -- 0-5
            cosdna_irritant INT,                        -- 0-5
            cosdna_safety   INT,                        -- 1-9
            cosing_annex    TEXT,                       -- 'II'|'III'|'IV'|'V'|'VI' or NULL
            cosing_restriction TEXT,
            id_rating       TEXT,                       -- INCIDecoder 'goodie'|'superstar'|null
            -- Provenance
            raw_payload     JSONB,                      -- everything we scraped (for re-parse)
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            fetch_status    TEXT NOT NULL
                            CHECK (fetch_status IN ('success','partial','failed','not_found')),
            error_message   TEXT,
            UNIQUE (ingredient_id, source)
        )
    """)
    op.execute("""
        CREATE INDEX ingredient_detail_sources_source_idx
        ON core.ingredient_detail_sources (source, fetched_at DESC)
    """)

    # ---- Aggregate: collated view per ingredient ----
    op.execute("""
        CREATE TABLE core.ingredient_detail (
            ingredient_id       BIGINT PRIMARY KEY REFERENCES core.ingredients(id) ON DELETE CASCADE,
            inci_name           TEXT,
            cas_number          TEXT,
            ec_number           TEXT,
            -- Canonical merged fields with provenance
            description         TEXT,
            description_source  TEXT,                       -- which source we picked
            functions           TEXT[],                     -- union from all sources
            ewg_hazard_low      INT,
            ewg_hazard_high     INT,
            ewg_concerns        JSONB,
            cosdna_acne         INT,
            cosdna_irritant     INT,
            cosing_annex        TEXT,
            cosing_restriction  TEXT,
            id_rating           TEXT,
            sources_used        TEXT[],                     -- e.g. {'ewg','incidecoder','cosing'}
            citation_urls       JSONB,                      -- {ewg:'…', incidecoder:'…', …}
            confidence_score    NUMERIC(3,2),               -- 0-1 based on source agreement
            collated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # ---- Queue for ingredient detail extraction ----
    op.execute("""
        CREATE TABLE scraping.ingredient_detail_queue (
            id              BIGSERIAL PRIMARY KEY,
            ingredient_id   BIGINT NOT NULL REFERENCES core.ingredients(id) ON DELETE CASCADE,
            source          TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','running','done','failed','not_found','skipped')),
            attempts        INT NOT NULL DEFAULT 0,
            last_error      TEXT,
            scheduled_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at    TIMESTAMPTZ,
            UNIQUE (ingredient_id, source)
        )
    """)
    op.execute("""
        CREATE INDEX ingredient_detail_queue_status_idx
        ON scraping.ingredient_detail_queue (status, scheduled_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraping.ingredient_detail_queue")
    op.execute("DROP TABLE IF EXISTS core.ingredient_detail")
    op.execute("DROP TABLE IF EXISTS core.ingredient_detail_sources")
    op.execute("DROP TABLE IF EXISTS scraping.ingredient_source_strategies")
