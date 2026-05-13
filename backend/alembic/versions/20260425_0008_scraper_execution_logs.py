"""Add scraping.scraper_execution_logs for per-scraper health monitoring

Tracks each scraper run (discovery + ingredient extraction + retailer scrape) so the
status dashboard can show 30-day uptime, last-success timestamp, and recent history.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE scraping.scraper_execution_logs (
            id              BIGSERIAL PRIMARY KEY,
            scraper_kind    TEXT NOT NULL,
                            -- 'retailer_discovery'  (Nykaa/Tira/Purplle)
                            -- 'retailer_listing'    (per-product fetch on a marketplace)
                            -- 'd2c_discovery'       (Shopify products.json)
                            -- 'ingredient_extract'  (per-product INCI from D2C site)
                            -- 'schema_detection'    (LLM brand strategy detection)
                            -- 'ingredient_detail'   (EWG/INCIDecoder/CosIng/COSDNA)
            scraper_target  TEXT NOT NULL,
                            -- e.g. 'nykaa', 'beminimalist.co', 'ewg', 'incidecoder'
            status          TEXT NOT NULL
                            CHECK (status IN ('success','partial','failed','no_data','running')),
            started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at     TIMESTAMPTZ,
            items_attempted INT,
            items_succeeded INT,
            items_failed    INT,
            error_message   TEXT,
            metadata        JSONB
        )
    """)
    op.execute("""
        CREATE INDEX scraper_execution_logs_kind_target_started_idx
        ON scraping.scraper_execution_logs (scraper_kind, scraper_target, started_at DESC)
    """)
    op.execute("""
        CREATE INDEX scraper_execution_logs_started_idx
        ON scraping.scraper_execution_logs (started_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraping.scraper_execution_logs")
