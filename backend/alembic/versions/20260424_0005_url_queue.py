"""Add scraping.url_queue for marketplace product URL discovery

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE scraping.url_queue (
            id          BIGSERIAL PRIMARY KEY,
            retailer_id INTEGER NOT NULL REFERENCES core.retailers(id) ON DELETE CASCADE,
            url         TEXT NOT NULL,
            category_hint TEXT,
            status      TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'scraped', 'failed')),
            attempts    INTEGER NOT NULL DEFAULT 0,
            error_msg   TEXT,
            discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            scraped_at  TIMESTAMPTZ,
            UNIQUE (retailer_id, url)
        )
    """)
    op.execute("CREATE INDEX url_queue_pending_idx ON scraping.url_queue (retailer_id, status, discovered_at) WHERE status = 'pending'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraping.url_queue")
