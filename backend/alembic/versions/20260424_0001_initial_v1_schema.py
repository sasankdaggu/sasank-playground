"""Initial v1 schema

Revision ID: 0001
Revises:
Create Date: 2026-04-24
"""
from __future__ import annotations

from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None

V1_SQL = Path(__file__).resolve().parent.parent.parent.parent / "spike" / "src" / "spike" / "schema" / "v1.sql"


def upgrade() -> None:
    op.execute(V1_SQL.read_text())


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")
    op.execute("DROP SCHEMA IF EXISTS users CASCADE")
    op.execute("DROP SCHEMA IF EXISTS scraping CASCADE")
    op.execute("DROP SCHEMA IF EXISTS taxonomy CASCADE")
