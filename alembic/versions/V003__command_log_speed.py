"""command_log: record speed when command sent

Revision ID: V003
Revises: V002
Create Date: 2026-04-30
"""

from alembic import op

revision = "V003"
down_revision = "V002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE command_log
    ADD COLUMN IF NOT EXISTS speed_kmh NUMERIC(8, 2);
""")


def downgrade() -> None:
    op.execute("ALTER TABLE command_log DROP COLUMN IF EXISTS speed_kmh;")
