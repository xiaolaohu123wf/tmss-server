"""track_segment: add segment_type column for loading/unloading labeling

Revision ID: V005
Revises: V004
Create Date: 2026-05-06
"""

from alembic import op

revision = "V005"
down_revision = "V004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE track_segment
    ADD COLUMN IF NOT EXISTS segment_type VARCHAR(20) NULL;

COMMENT ON COLUMN track_segment.segment_type IS
    'NULL=普通行驶段; loading=装料驻留段; unloading=卸料驻留段';
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE track_segment DROP COLUMN IF EXISTS segment_type;
""")
