"""business_config: add map default zoom level

Revision ID: V008
Revises: V007
Create Date: 2026-05-07
"""

from alembic import op

revision = "V008"
down_revision = "V007"
branch_labels = None
depends_on = None

_DEFAULT_ZOOM = 16


def upgrade() -> None:
    op.execute(f"""
ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS map_zoom SMALLINT NOT NULL DEFAULT {_DEFAULT_ZOOM};
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE business_config
    DROP COLUMN IF EXISTS map_zoom;
""")
