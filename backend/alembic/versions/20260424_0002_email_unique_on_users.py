"""Add unique constraint on users.email

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24
"""
from __future__ import annotations
from alembic import op

revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users.users ADD CONSTRAINT users_email_unique UNIQUE (email)")


def downgrade() -> None:
    op.execute("ALTER TABLE users.users DROP CONSTRAINT IF EXISTS users_email_unique")
