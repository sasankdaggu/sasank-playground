"""Add scraping.ingredient_strategies for LLM-detected per-brand extraction rules

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-25
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE scraping.ingredient_strategies (
            id              BIGSERIAL PRIMARY KEY,
            brand_domain    TEXT NOT NULL UNIQUE,   -- e.g. 'beminimalist.co'
            brand_name      TEXT NOT NULL,
            brand_url       TEXT NOT NULL,          -- canonical homepage URL

            -- Detection result
            platform        TEXT,                   -- 'shopify', 'custom', null=unknown
            css_selector    TEXT,                   -- selector for the INCI text container
            requires_js     BOOLEAN NOT NULL DEFAULT false,
            js_action       TEXT,                   -- e.g. 'click .see-full-ingredients'
            notes           TEXT,                   -- LLM-generated extraction notes

            -- Validation evidence
            sample_url      TEXT,                   -- product page used for detection
            sample_inci_preview TEXT,               -- first 200 chars of extracted INCI

            -- Quality
            confidence      NUMERIC(3,2),           -- 0.00-1.00 (LLM self-reported)
            detection_model TEXT,
            detected_at     TIMESTAMPTZ,

            -- Lifecycle
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN (
                                'pending',          -- not yet detected
                                'active',           -- selector validated and working
                                'needs_review',     -- low confidence or partial result
                                'failed',           -- detection failed
                                'no_inci'           -- brand does not expose INCI in HTML
                            )),
            last_validated_at TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ingredient_strategies_status_idx
        ON scraping.ingredient_strategies (status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraping.ingredient_strategies")
