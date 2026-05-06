"""轨迹分段 v1.2.0 重构：段点解耦、枚举扩展、dwell 单位改为秒

Revision ID: V007
Revises: V006
Create Date: 2026-05-07

变更摘要
--------
1. work_state_t ENUM  ← 新增 'idle' 值
2. business_config    ← loading_dwell_min → loading_dwell_s（值×60）
                       unloading_dwell_min → unloading_dwell_s（值×60）
                       新增 segment_buffer_min（默认 3 分钟显示缓冲）
3. location_point     ← 删除 segment_id 列及 idx_lp_segment 索引
4. track_segment      ← 新增 idx_seg_ended_at 索引（加速 sweeper 查询）
"""

from alembic import op

revision = "V007"
down_revision = "V006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
-- ── 1. work_state_t 枚举扩展 ──────────────────────────────────────────────
ALTER TYPE work_state_t ADD VALUE IF NOT EXISTS 'idle';

-- ── 2. business_config：dwell 单位改为秒 + 新增 segment_buffer_min ────────
ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS segment_buffer_min SMALLINT NOT NULL DEFAULT 3;

-- 用 DEFAULT+NOT NULL 三步完成无锁重命名：
--   a) 新列 = 旧列 × 60  b) 删旧列
ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS loading_dwell_s   SMALLINT;
UPDATE business_config
    SET loading_dwell_s = loading_dwell_min * 60
    WHERE loading_dwell_s IS NULL;
ALTER TABLE business_config
    ALTER COLUMN loading_dwell_s SET NOT NULL,
    ALTER COLUMN loading_dwell_s SET DEFAULT 300;
ALTER TABLE business_config
    DROP COLUMN IF EXISTS loading_dwell_min;

ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS unloading_dwell_s SMALLINT;
UPDATE business_config
    SET unloading_dwell_s = unloading_dwell_min * 60
    WHERE unloading_dwell_s IS NULL;
ALTER TABLE business_config
    ALTER COLUMN unloading_dwell_s SET NOT NULL,
    ALTER COLUMN unloading_dwell_s SET DEFAULT 300;
ALTER TABLE business_config
    DROP COLUMN IF EXISTS unloading_dwell_min;

COMMENT ON COLUMN business_config.loading_dwell_s IS
    '装料区最短驻留时长（秒），默认 300 s';
COMMENT ON COLUMN business_config.unloading_dwell_s IS
    '卸料区最短驻留时长（秒），默认 300 s';
COMMENT ON COLUMN business_config.segment_buffer_min IS
    '运料/空载段展示缓冲（分钟），前端查询时前后各扩展此值，默认 3 min';

-- ── 3. location_point：删除 segment_id ────────────────────────────────────
DROP INDEX  IF EXISTS idx_lp_segment;
ALTER TABLE location_point DROP COLUMN IF EXISTS segment_id;

-- ── 4. track_segment：补充索引 ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_seg_ended_at
    ON track_segment (ended_at)
    WHERE ended_at IS NULL;
""")


def downgrade() -> None:
    op.execute("""
-- 恢复 segment_id 列（数据无法还原，仅恢复结构）
ALTER TABLE location_point
    ADD COLUMN IF NOT EXISTS segment_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_lp_segment ON location_point (segment_id);

-- 恢复 business_config 字段
ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS loading_dwell_min SMALLINT;
UPDATE business_config SET loading_dwell_min = loading_dwell_s / 60;
ALTER TABLE business_config
    ALTER COLUMN loading_dwell_min SET NOT NULL,
    ALTER COLUMN loading_dwell_min SET DEFAULT 5;
ALTER TABLE business_config DROP COLUMN IF EXISTS loading_dwell_s;

ALTER TABLE business_config
    ADD COLUMN IF NOT EXISTS unloading_dwell_min SMALLINT;
UPDATE business_config SET unloading_dwell_min = unloading_dwell_s / 60;
ALTER TABLE business_config
    ALTER COLUMN unloading_dwell_min SET NOT NULL,
    ALTER COLUMN unloading_dwell_min SET DEFAULT 5;
ALTER TABLE business_config DROP COLUMN IF EXISTS unloading_dwell_s;

ALTER TABLE business_config DROP COLUMN IF EXISTS segment_buffer_min;

DROP INDEX IF EXISTS idx_seg_ended_at;
""")
