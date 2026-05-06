"""business_config: add transport_timeout_min for unknown-state detection

Revision ID: V006
Revises: V005
Create Date: 2026-05-06
"""

from alembic import op

revision = "V006"
down_revision = "V005"
branch_labels = None
depends_on = None

_DEFAULT_TIMEOUT_MIN = 30


def upgrade() -> None:
    op.execute(f"""
ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS transport_timeout_min INT NOT NULL DEFAULT {_DEFAULT_TIMEOUT_MIN};

COMMENT ON COLUMN business_config.transport_timeout_min IS
    '运输超时阈值（分钟）：车辆离开装/卸料区后超过此时长仍未抵达下一站，标记为状态未知';
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE business_config DROP COLUMN IF EXISTS transport_timeout_min;
""")
