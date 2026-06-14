"""track_segment: add distance_km (预计算里程，消除列表查询实时扫描 location_point)

Revision ID: V011
Revises: V010
Create Date: 2026-05-15
"""

from alembic import op

revision = "V011"
down_revision = "V010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE track_segment
    ADD COLUMN IF NOT EXISTS distance_km NUMERIC(10,3);
""")
    # 索引：后台补填时按 ended_at DESC 扫描空值，加速 WHERE distance_km IS NULL 过滤
    # 注意：CONCURRENTLY 不能在事务块内执行，故使用普通 CREATE INDEX（迁移期间表锁极短）
    op.execute("""
CREATE INDEX IF NOT EXISTS idx_seg_null_distance
    ON track_segment (ended_at DESC)
    WHERE distance_km IS NULL AND ended_at IS NOT NULL;
""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_seg_null_distance;")
    op.execute("ALTER TABLE track_segment DROP COLUMN IF EXISTS distance_km;")
