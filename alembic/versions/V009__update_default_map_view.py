"""Update default map center + zoom for existing business_config row

Revision ID: V009
Revises: V008
Create Date: 2026-05-07
"""

from alembic import op

revision = "V009"
down_revision = "V008"
branch_labels = None
depends_on = None

_DEFAULT_LNG = 109.2695
_DEFAULT_LAT = 30.383164
_DEFAULT_ZOOM = 15


def upgrade() -> None:
    op.execute(f"""
UPDATE business_config
SET map_center_lng = {_DEFAULT_LNG},
    map_center_lat = {_DEFAULT_LAT},
    map_zoom = {_DEFAULT_ZOOM}
WHERE id = 1;
""")


def downgrade() -> None:
    op.execute("""
UPDATE business_config
SET map_center_lng = 109.4753,
    map_center_lat = 30.2832,
    map_zoom = 16
WHERE id = 1;
""")
