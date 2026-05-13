"""add thumb_url and shelf_url to core.products

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("thumb_url", sa.Text(), nullable=True), schema="core")
    op.add_column("products", sa.Column("shelf_url", sa.Text(), nullable=True), schema="core")


def downgrade() -> None:
    op.drop_column("products", "thumb_url", schema="core")
    op.drop_column("products", "shelf_url", schema="core")
