"""Add ingredients_raw to core.products

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-25
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE core.products ADD COLUMN IF NOT EXISTS ingredients_raw TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE core.products DROP COLUMN IF EXISTS ingredients_raw")
