"""Add onboarding tracking columns to users table

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-29
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users.users
          ADD COLUMN IF NOT EXISTS onboarding_step TEXT DEFAULT NULL,
          ADD COLUMN IF NOT EXISTS goals JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS skin_profile JSONB NOT NULL DEFAULT '{}'::jsonb
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users.users
          DROP COLUMN IF EXISTS onboarding_step,
          DROP COLUMN IF EXISTS goals,
          DROP COLUMN IF EXISTS skin_profile
    """)
