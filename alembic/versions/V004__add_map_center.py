"""business_config: add default map center (lng/lat)

Revision ID: V004
Revises: V003
Create Date: 2026-05-06
"""

from alembic import op

revision = "V004"
down_revision = "V003"
branch_labels = None
depends_on = None

# 默认中心点：恩施市（与代码原硬编码值保持一致）
_DEFAULT_LNG = 109.4753
_DEFAULT_LAT = 30.2832


def upgrade() -> None:
    op.execute(f"""
ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS map_center_lng NUMERIC(10, 7) NOT NULL DEFAULT {_DEFAULT_LNG},
    ADD COLUMN IF NOT EXISTS map_center_lat NUMERIC(10, 7) NOT NULL DEFAULT {_DEFAULT_LAT};
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE business_config
    DROP COLUMN IF EXISTS map_center_lng,
    DROP COLUMN IF EXISTS map_center_lat;
""")
