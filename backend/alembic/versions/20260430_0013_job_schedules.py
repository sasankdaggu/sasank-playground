"""Add scraping.job_schedules for automated scraper cadence

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-30
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE scraping.job_schedules (
            job_id          TEXT PRIMARY KEY,
            display_name    TEXT NOT NULL,
            enabled         BOOLEAN NOT NULL DEFAULT false,
            cron            TEXT,           -- NULL = manual-trigger only
            last_run_at     TIMESTAMPTZ,
            next_run_at     TIMESTAMPTZ,
            last_status     TEXT,           -- 'running' | 'success' | 'failed'
            last_log_id     BIGINT REFERENCES scraping.scraper_execution_logs(id)
        )
    """)
    op.execute("""
        INSERT INTO scraping.job_schedules (job_id, display_name, enabled, cron)
        VALUES
            ('nykaa_scrape', 'Nykaa full catalogue scrape', false, NULL)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraping.job_schedules")
