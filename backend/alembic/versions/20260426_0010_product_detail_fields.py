"""Add extended product detail fields to core.products

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-26
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core.products
          ADD COLUMN IF NOT EXISTS category_raw        VARCHAR(255),
          ADD COLUMN IF NOT EXISTS subcategory_raw     VARCHAR(255),
          ADD COLUMN IF NOT EXISTS pack_size           VARCHAR(100),
          ADD COLUMN IF NOT EXISTS how_to_use          TEXT,
          ADD COLUMN IF NOT EXISTS skin_type           JSONB,
          ADD COLUMN IF NOT EXISTS skin_concerns       JSONB,
          ADD COLUMN IF NOT EXISTS country_of_origin   VARCHAR(100),
          ADD COLUMN IF NOT EXISTS key_ingredients_raw TEXT,
          ADD COLUMN IF NOT EXISTS claims              JSONB
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE core.products
          DROP COLUMN IF EXISTS category_raw,
          DROP COLUMN IF EXISTS subcategory_raw,
          DROP COLUMN IF EXISTS pack_size,
          DROP COLUMN IF EXISTS how_to_use,
          DROP COLUMN IF EXISTS skin_type,
          DROP COLUMN IF EXISTS skin_concerns,
          DROP COLUMN IF EXISTS country_of_origin,
          DROP COLUMN IF EXISTS key_ingredients_raw,
          DROP COLUMN IF EXISTS claims
    """)
