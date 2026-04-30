"""add driver_name to vehicle

Revision ID: V002
Revises: V001
Create Date: 2026-04-30
"""

from alembic import op

revision = "V002"
down_revision = "V001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE vehicle
    ADD COLUMN IF NOT EXISTS driver_name VARCHAR(50);
""")


def downgrade() -> None:
    op.execute("ALTER TABLE vehicle DROP COLUMN IF EXISTS driver_name;")
