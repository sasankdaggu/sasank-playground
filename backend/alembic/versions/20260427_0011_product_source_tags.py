"""Add source_tags JSONB column to core.products

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-27
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core.products
          ADD COLUMN IF NOT EXISTS source_tags JSONB
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE core.products
          DROP COLUMN IF EXISTS source_tags
    """)
