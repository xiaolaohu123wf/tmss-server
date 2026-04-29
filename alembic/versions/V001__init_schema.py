"""init schema

Revision ID: V001
Revises:
Create Date: 2026-04-29
"""

from alembic import op

revision = "V001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
-- ─────────────────────────────────────────────────────────
--  公共函数与枚举类型
-- ─────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TYPE loc_type_t   AS ENUM ('gps', 'lbs');
CREATE TYPE work_state_t AS ENUM ('loading', 'unloading', 'transport_loaded', 'transport_empty', 'unknown');
CREATE TYPE cmd_source_t AS ENUM ('auto', 'manual');
CREATE TYPE user_role_t  AS ENUM ('manager', 'fleet_captain', 'terminal');

-- ─────────────────────────────────────────────────────────
--  1. fleet — 车队
-- ─────────────────────────────────────────────────────────
CREATE TABLE fleet (
  id         BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       VARCHAR(100) NOT NULL,
  notes      TEXT,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_fleet_name UNIQUE (name)
);

CREATE TRIGGER trg_fleet_updated_at
  BEFORE UPDATE ON fleet
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  2. vehicle — 车辆主数据
-- ─────────────────────────────────────────────────────────
CREATE TABLE vehicle (
  id            BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fleet_id      BIGINT,
  license_plate VARCHAR(20)  NOT NULL,
  vehicle_type  VARCHAR(30)  NOT NULL DEFAULT '',
  load_capacity NUMERIC(8,2),
  notes         TEXT,
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_license_plate UNIQUE (license_plate)
);

CREATE INDEX idx_vehicle_fleet  ON vehicle (fleet_id)      WHERE deleted_at IS NULL;
CREATE INDEX idx_vehicle_active ON vehicle (license_plate) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_vehicle_updated_at
  BEFORE UPDATE ON vehicle
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  3. device — 终端设备
-- ─────────────────────────────────────────────────────────
CREATE TABLE device (
  id               BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  imei             CHAR(15)    NOT NULL,
  iccid            VARCHAR(20),
  model            VARCHAR(50),
  firmware_version VARCHAR(50),
  notes            TEXT,
  deleted_at       TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_imei UNIQUE (imei)
);

CREATE TRIGGER trg_device_updated_at
  BEFORE UPDATE ON device
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  4. driver — 驾驶员
-- ─────────────────────────────────────────────────────────
CREATE TABLE driver (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fleet_id   BIGINT,
  name       VARCHAR(50) NOT NULL,
  license_no VARCHAR(30),
  phone      VARCHAR(20),
  notes      TEXT,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_driver_fleet ON driver (fleet_id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_driver_updated_at
  BEFORE UPDATE ON driver
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  5. device_vehicle_bind — 设备·车辆·驾驶员绑定历史
-- ─────────────────────────────────────────────────────────
CREATE TABLE device_vehicle_bind (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id  BIGINT      NOT NULL,
  vehicle_id BIGINT      NOT NULL,
  driver_id  BIGINT,
  bound_at   TIMESTAMPTZ NOT NULL,
  unbound_at TIMESTAMPTZ,
  operator   VARCHAR(50),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bind_device  ON device_vehicle_bind (device_id);
CREATE INDEX idx_bind_vehicle ON device_vehicle_bind (vehicle_id);
CREATE INDEX idx_bind_driver  ON device_vehicle_bind (driver_id);

CREATE UNIQUE INDEX uq_bind_device_active  ON device_vehicle_bind (device_id)  WHERE unbound_at IS NULL;
CREATE UNIQUE INDEX uq_bind_vehicle_active ON device_vehicle_bind (vehicle_id) WHERE unbound_at IS NULL;

-- ─────────────────────────────────────────────────────────
--  6. geo_zone — 地理围栏与区域
-- ─────────────────────────────────────────────────────────
CREATE TABLE geo_zone (
  id          BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        VARCHAR(100) NOT NULL,
  zone_type   VARCHAR(30)  NOT NULL,
  coordinates JSONB        NOT NULL,
  speed_limit SMALLINT,
  dwell_min   SMALLINT,
  is_enabled  BOOLEAN      NOT NULL DEFAULT TRUE,
  extra       JSONB,
  notes       TEXT,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_geo_zone_type    ON geo_zone (zone_type);
CREATE INDEX idx_geo_zone_enabled ON geo_zone (is_enabled);
CREATE INDEX idx_geo_zone_coords  ON geo_zone USING GIN (coordinates);

CREATE TRIGGER trg_geo_zone_updated_at
  BEFORE UPDATE ON geo_zone
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  7. operation_ban — 禁止运营时段规则
-- ─────────────────────────────────────────────────────────
CREATE TABLE operation_ban (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  zone_id    BIGINT,
  start_time TIME        NOT NULL,
  end_time   TIME        NOT NULL,
  weekdays   SMALLINT[]  NOT NULL DEFAULT '{1,2,3,4,5,6,7}',
  is_enabled BOOLEAN     NOT NULL DEFAULT TRUE,
  notes      TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ban_zone    ON operation_ban (zone_id);
CREATE INDEX idx_ban_enabled ON operation_ban (is_enabled);

CREATE TRIGGER trg_operation_ban_updated_at
  BEFORE UPDATE ON operation_ban
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  8. business_config — 业务运营参数（全局单行）
-- ─────────────────────────────────────────────────────────
CREATE TABLE business_config (
  id                  BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  global_speed_limit  SMALLINT    NOT NULL DEFAULT 80,
  park_threshold_min  SMALLINT    NOT NULL DEFAULT 10,
  loading_dwell_min   SMALLINT    NOT NULL DEFAULT 5,
  unloading_dwell_min SMALLINT    NOT NULL DEFAULT 5,
  alert_cooldown_s    SMALLINT    NOT NULL DEFAULT 10,
  hb_timeout_s        SMALLINT    NOT NULL DEFAULT 90,
  weather_city        VARCHAR(50) NOT NULL DEFAULT 'Nanjing',
  weather_cache_min   SMALLINT    NOT NULL DEFAULT 30,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO business_config DEFAULT VALUES;

CREATE TRIGGER trg_business_config_updated_at
  BEFORE UPDATE ON business_config
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  9. location_point — 高频定位点（按月分区）
-- ─────────────────────────────────────────────────────────
CREATE TABLE location_point (
  id          BIGINT         GENERATED ALWAYS AS IDENTITY,
  device_id   BIGINT         NOT NULL,
  vehicle_id  BIGINT,
  segment_id  BIGINT,
  recorded_at TIMESTAMPTZ    NOT NULL,
  lat         NUMERIC(10,7)  NOT NULL,
  lng         NUMERIC(10,7)  NOT NULL,
  speed       NUMERIC(6,2),
  altitude    NUMERIC(8,2),
  loc_type    loc_type_t     NOT NULL DEFAULT 'gps',
  created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
  PRIMARY KEY (id, recorded_at)
) PARTITION BY RANGE (recorded_at);

CREATE INDEX idx_lp_device_time  ON location_point (device_id,  recorded_at);
CREATE INDEX idx_lp_vehicle_time ON location_point (vehicle_id, recorded_at);
CREATE INDEX idx_lp_segment      ON location_point (segment_id);
CREATE INDEX idx_lp_time_brin    ON location_point USING BRIN (recorded_at);

-- 初始分区：当前月 + 未来 2 个月
CREATE TABLE location_point_2026_04 PARTITION OF location_point
  FOR VALUES FROM ('2026-04-01 00:00:00+00') TO ('2026-05-01 00:00:00+00');
CREATE TABLE location_point_2026_05 PARTITION OF location_point
  FOR VALUES FROM ('2026-05-01 00:00:00+00') TO ('2026-06-01 00:00:00+00');
CREATE TABLE location_point_2026_06 PARTITION OF location_point
  FOR VALUES FROM ('2026-06-01 00:00:00+00') TO ('2026-07-01 00:00:00+00');

-- ─────────────────────────────────────────────────────────
--  10. track_segment — 轨迹段
-- ─────────────────────────────────────────────────────────
CREATE TABLE track_segment (
  id          BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id   BIGINT         NOT NULL,
  vehicle_id  BIGINT,
  started_at  TIMESTAMPTZ    NOT NULL,
  ended_at    TIMESTAMPTZ,
  start_lat   NUMERIC(10,7),
  start_lng   NUMERIC(10,7),
  end_lat     NUMERIC(10,7),
  end_lng     NUMERIC(10,7),
  point_count INT            NOT NULL DEFAULT 0,
  label       VARCHAR(100),
  created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_seg_device_start  ON track_segment (device_id,  started_at);
CREATE INDEX idx_seg_vehicle_start ON track_segment (vehicle_id, started_at);

CREATE TRIGGER trg_track_segment_updated_at
  BEFORE UPDATE ON track_segment
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  11. work_session — 作业状态会话
-- ─────────────────────────────────────────────────────────
CREATE TABLE work_session (
  id         BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  vehicle_id BIGINT       NOT NULL,
  state      work_state_t NOT NULL,
  zone_id    BIGINT,
  started_at TIMESTAMPTZ  NOT NULL,
  ended_at   TIMESTAMPTZ,
  duration_s INT,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ws_vehicle_start ON work_session (vehicle_id, started_at);
CREATE INDEX idx_ws_zone          ON work_session (zone_id);

-- ─────────────────────────────────────────────────────────
--  12. event — 统一事件与告警留痕
-- ─────────────────────────────────────────────────────────
CREATE TABLE event (
  id          BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id   BIGINT,
  vehicle_id  BIGINT,
  event_type  VARCHAR(40)    NOT NULL,
  severity    SMALLINT       NOT NULL DEFAULT 2,
  zone_id     BIGINT,
  ban_id      BIGINT,
  lat         NUMERIC(10,7),
  lng         NUMERIC(10,7),
  speed       NUMERIC(6,2),
  cmd_sent    VARCHAR(10),
  detail      JSONB,
  occurred_at TIMESTAMPTZ    NOT NULL,
  created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_event_vehicle_time ON event (vehicle_id, occurred_at);
CREATE INDEX idx_event_device_time  ON event (device_id,  occurred_at);
CREATE INDEX idx_event_type         ON event (event_type);
CREATE INDEX idx_event_zone         ON event (zone_id);
CREATE INDEX idx_event_detail_gin   ON event USING GIN (detail);

-- ─────────────────────────────────────────────────────────
--  13. command_log — 下行指令记录
-- ─────────────────────────────────────────────────────────
CREATE TABLE command_log (
  id           BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id    BIGINT,
  vehicle_id   BIGINT,
  cmd          VARCHAR(20)  NOT NULL,
  source       cmd_source_t NOT NULL DEFAULT 'auto',
  operator_id  BIGINT,
  event_id     BIGINT,
  is_delivered BOOLEAN      NOT NULL DEFAULT FALSE,
  sent_at      TIMESTAMPTZ  NOT NULL,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cmd_device_time  ON command_log (device_id,  sent_at);
CREATE INDEX idx_cmd_vehicle_time ON command_log (vehicle_id, sent_at);

-- ─────────────────────────────────────────────────────────
--  14. app_user — 用户与角色
-- ─────────────────────────────────────────────────────────
CREATE TABLE app_user (
  id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username      VARCHAR(50) NOT NULL,
  password_hash TEXT        NOT NULL,
  role          user_role_t NOT NULL DEFAULT 'fleet_captain',
  fleet_id      BIGINT,
  is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_username UNIQUE (username),
  CONSTRAINT chk_fleet_captain_fleet
    CHECK (role != 'fleet_captain' OR fleet_id IS NOT NULL)
);

CREATE INDEX idx_user_active ON app_user (username) WHERE deleted_at IS NULL;
CREATE INDEX idx_user_fleet  ON app_user (fleet_id)  WHERE deleted_at IS NULL;

CREATE TRIGGER trg_app_user_updated_at
  BEFORE UPDATE ON app_user
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────
--  15. sys_config — 系统/部署参数（仅展示，不影响运行时）
-- ─────────────────────────────────────────────────────────
CREATE TABLE sys_config (
  config_key  VARCHAR(60)  NOT NULL PRIMARY KEY,
  value       TEXT         NOT NULL,
  description VARCHAR(200),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

INSERT INTO sys_config (config_key, value, description) VALUES
  ('tcp_port',          '9000',  'TCP 监听端口（仅展示，以环境变量为准）'),
  ('http_port',         '8080',  'HTTP 管理界面端口（仅展示，以环境变量为准）'),
  ('gps_filter_enable', '1',     'GPS卡尔曼滤波开关 1=启用 0=关闭'),
  ('gps_filter_alpha',  '0.2',   'GPS卡尔曼滤波系数 α，范围 0~1');

CREATE TRIGGER trg_sys_config_updated_at
  BEFORE UPDATE ON sys_config
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("""
DROP TABLE IF EXISTS sys_config CASCADE;
DROP TABLE IF EXISTS app_user CASCADE;
DROP TABLE IF EXISTS command_log CASCADE;
DROP TABLE IF EXISTS event CASCADE;
DROP TABLE IF EXISTS work_session CASCADE;
DROP TABLE IF EXISTS track_segment CASCADE;
DROP TABLE IF EXISTS location_point CASCADE;
DROP TABLE IF EXISTS business_config CASCADE;
DROP TABLE IF EXISTS operation_ban CASCADE;
DROP TABLE IF EXISTS geo_zone CASCADE;
DROP TABLE IF EXISTS device_vehicle_bind CASCADE;
DROP TABLE IF EXISTS driver CASCADE;
DROP TABLE IF EXISTS device CASCADE;
DROP TABLE IF EXISTS vehicle CASCADE;
DROP TABLE IF EXISTS fleet CASCADE;
DROP FUNCTION IF EXISTS set_updated_at CASCADE;
DROP TYPE IF EXISTS user_role_t CASCADE;
DROP TYPE IF EXISTS cmd_source_t CASCADE;
DROP TYPE IF EXISTS work_state_t CASCADE;
DROP TYPE IF EXISTS loc_type_t CASCADE;
    """)
