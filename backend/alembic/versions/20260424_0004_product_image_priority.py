"""add image_priority to core.products and unique constraint on brand+name

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_priority", sa.Integer(), nullable=False, server_default="99"), schema="core")
    op.create_unique_constraint("products_brand_name_unique", "products", ["brand_id", "canonical_name"], schema="core")


def downgrade() -> None:
    op.drop_constraint("products_brand_name_unique", "products", schema="core")
    op.drop_column("products", "image_priority", schema="core")
