"""vehicle: add driver_phone (驾驶员电话)

Revision ID: V010
Revises: V009
Create Date: 2026-05-07
"""

from alembic import op

revision = "V010"
down_revision = "V009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE vehicle
    ADD COLUMN IF NOT EXISTS driver_phone VARCHAR(30);
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE vehicle DROP COLUMN IF EXISTS driver_phone;
""")
