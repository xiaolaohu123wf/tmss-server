# TMSS 数据库设计

> 引擎：PostgreSQL 16+  
> 库名：`tmss_db`  
> 时区：所有时间字段使用 `TIMESTAMPTZ`（带时区），统一存储 UTC，展示时由应用层/客户端转换本地时间  

---

## 通用约定

- 主键：`BIGINT GENERATED ALWAYS AS IDENTITY`，命名为 `id`。
- 时间审计：业务表统一保留 `created_at`、`updated_at`（`TIMESTAMPTZ`），`updated_at` 通过触发器自动维护，替代 MySQL 的 `ON UPDATE CURRENT_TIMESTAMP`。
- 软删除：有留痕需求的表增加 `deleted_at TIMESTAMPTZ NULL DEFAULT NULL`，`NULL` 表示未删除；配合**部分索引**加速活跃记录查询。
- 坐标系：`location_point` 存设备上报的原始 **WGS-84** 坐标；`geo_zone` 围栏坐标存 **GCJ-02**（火星）；服务层在空间判定前做转换。
- 围栏几何：统一用 `JSONB` 字段存 `[[lng, lat], ...]` 坐标数组，应用层做点在多边形判定；扩展时可迁移至 PostGIS `GEOMETRY` 类型。
- 枚举值：使用 `CREATE TYPE ... AS ENUM` 定义，类型安全且可列出合法值；需在线新增枚举值时用 `ALTER TYPE ... ADD VALUE`。
- JSON 字段：统一使用 `JSONB`（二进制存储，支持 GIN 索引），不使用 `JSON`。
- 密码存储：使用 **bcrypt**（cost ≥ 12）哈希后存 `TEXT`，**禁止** SHA-256/MD5 直接存储。
- 保留字规避：PostgreSQL 内置 `user` 为保留字，用户表命名为 `app_user`。

---

## 建库语句

```sql
CREATE DATABASE tmss_db
  ENCODING    = 'UTF8'
  LC_COLLATE  = 'zh_CN.UTF-8'
  LC_CTYPE    = 'zh_CN.UTF-8'
  TEMPLATE    = template0;

\c tmss_db;
```

---

## 公共函数与类型

### `updated_at` 自动更新触发器

> 所有含 `updated_at` 字段的表均需绑定此触发器，替代 MySQL 的 `ON UPDATE CURRENT_TIMESTAMP`。

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;
```

### ENUM 类型定义

```sql
CREATE TYPE loc_type_t     AS ENUM ('gps', 'lbs');
CREATE TYPE work_state_t   AS ENUM ('loading', 'unloading', 'transport_loaded', 'transport_empty', 'unknown', 'idle');
CREATE TYPE cmd_source_t   AS ENUM ('auto', 'manual');
CREATE TYPE user_role_t    AS ENUM ('manager', 'fleet_captain', 'terminal');
```

> **v1.2.0**：`work_state_t` 新增 `idle`（停车闲置，不在装/卸料区的长时停车），对应大屏浅灰色 `#d9d9d9`。

---

## 角色权限速览

| 权限项 | 管理者 `manager` | 车队长 `fleet_captain` | 终端用户 `terminal` |
| --- | :---: | :---: | :---: |
| 登录后台管理界面 | ✓ | ✓ | ✗ |
| 大屏实时查看 | ✓ 全部车辆 | ✓ 仅本车队车辆 | ✗ |
| 登记 / 管理车辆信息 | ✓ 全部 | ✓ 仅本车队 | ✗ |
| 驾驶员管理 | ✓ 全部 | ✓ 仅本车队 | ✗ |
| 设备绑定与解绑 | ✓ 全部 | ✓ 仅本车队 | ✗ |
| 查看历史轨迹 / 事件告警 | ✓ 全部 | ✓ 仅本车队 | ✗ |
| 配置围栏 / 区域 | ✓ | ✓ | ✗ |
| 修改业务参数（限速/驻留阈值等） | ✓ | ✗ | ✗ |
| 禁运时段配置 | ✓ | ✗ | ✗ |
| 系统设置（高危操作） | ✓ **需二次输入管理员密码** | ✗ | ✗ |
| 管理用户账号（新增/禁用） | ✓ | ✗ | ✗ |
| TCP 设备数据上报 | — | — | ✓（硬件终端） |

> **终端用户**对应使用硬件终端（ESP32）的驾驶员，通过 IMEI 标识，不持有后台账号；`app_user` 中的 `terminal` 角色保留以备未来移动端扩展。  
> **二次验证**：管理者执行系统设置类操作时，前端需弹出密码确认弹窗，服务端重新校验当前用户密码，验证通过后方可提交变更；无需独立 admin 账号。  
> **数据隔离**：车队长的数据范围由 `app_user.fleet_id` 决定，服务层在所有查询中自动附加 `fleet_id` 过滤条件，前端无法绕过。

---

## 表结构

### 1. `fleet` — 车队

> 车队是数据隔离的基本单元。车队长账号通过 `app_user.fleet_id` 与其绑定，只能访问本车队下的车辆与数据。

```sql
CREATE TABLE fleet (
  id         BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       VARCHAR(100) NOT NULL,                    -- 车队名称
  notes      TEXT,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_fleet_name UNIQUE (name)
);

CREATE TRIGGER trg_fleet_updated_at
  BEFORE UPDATE ON fleet
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

### 2. `vehicle` — 车辆主数据

```sql
CREATE TABLE vehicle (
  id            BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fleet_id      BIGINT,                                -- FK fleet.id，所属车队
  license_plate VARCHAR(20)  NOT NULL,                -- 车牌号
  vehicle_type  VARCHAR(30)  NOT NULL DEFAULT '',     -- 车型：truck/loader/passenger_car/other
  load_capacity NUMERIC(8,2),                         -- 额定载重(吨)；passenger_car 时强制 NULL
  driver_name   VARCHAR(50),                          -- 驾驶员姓名（V002 迁移新增）
  notes         TEXT,
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_license_plate UNIQUE (license_plate)
);

CREATE INDEX idx_vehicle_fleet  ON vehicle (fleet_id) WHERE deleted_at IS NULL;
-- 部分索引：仅对未删除车辆建索引，加速活跃记录查询
CREATE INDEX idx_vehicle_active ON vehicle (license_plate) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_vehicle_updated_at
  BEFORE UPDATE ON vehicle
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

> **`vehicle_type` 合法值**：`truck`（货车）、`loader`（装载机）、`passenger_car`（家用车）、`other`（其他）。  
> `passenger_car` 类型的 `load_capacity` 在服务层强制置 `NULL`（Pydantic `model_validator` + SQL `CASE` 双重保障）。

---

### 3. `device` — 终端设备

```sql
CREATE TABLE device (
  id               BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  imei             CHAR(15)    NOT NULL,              -- 设备IMEI，与上报协议字段对齐
  iccid            VARCHAR(20),                       -- SIM卡ICCID
  model            VARCHAR(50),                       -- 硬件型号
  firmware_version VARCHAR(50),                       -- 固件版本
  notes            TEXT,
  deleted_at       TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_imei UNIQUE (imei)
);

CREATE TRIGGER trg_device_updated_at
  BEFORE UPDATE ON device
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

### 4. `driver` — 驾驶员

> `fleet_id` 记录驾驶员当前归属车队，用于支持「车队长仅管理本车队驾驶员」的数据隔离查询。  
> 历史调度记录（驾驶员曾驾驶哪辆车）通过 `device_vehicle_bind.driver_id` 追溯，与当前 `fleet_id` 无关。

```sql
CREATE TABLE driver (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fleet_id   BIGINT,                                  -- FK fleet.id；所属车队，NULL=暂未分配
  name       VARCHAR(50) NOT NULL,                    -- 姓名
  license_no VARCHAR(30),                             -- 驾驶证号
  phone      VARCHAR(20),                             -- 联系电话
  notes      TEXT,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_driver_fleet ON driver (fleet_id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_driver_updated_at
  BEFORE UPDATE ON driver
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

### 5. `device_vehicle_bind` — 设备·车辆·驾驶员绑定历史

> 通过**部分唯一索引**（`WHERE unbound_at IS NULL`）在数据库层面强制：同一设备/车辆同一时刻只允许一条绑定记录，无需额外应用层校验。

```sql
CREATE TABLE device_vehicle_bind (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id  BIGINT      NOT NULL,                    -- FK device.id
  vehicle_id BIGINT      NOT NULL,                    -- FK vehicle.id
  driver_id  BIGINT,                                  -- FK driver.id，可为空（暂无驾驶员）
  bound_at   TIMESTAMPTZ NOT NULL,                    -- 绑定时间
  unbound_at TIMESTAMPTZ,                             -- 解绑时间，NULL=当前仍绑定
  operator   VARCHAR(50),                             -- 操作人用户名
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bind_device  ON device_vehicle_bind (device_id);
CREATE INDEX idx_bind_vehicle ON device_vehicle_bind (vehicle_id);
CREATE INDEX idx_bind_driver  ON device_vehicle_bind (driver_id);

-- 部分唯一索引：数据库层面保证同一设备/车辆同时只有一条在绑记录
CREATE UNIQUE INDEX uq_bind_device_active  ON device_vehicle_bind (device_id)  WHERE unbound_at IS NULL;
CREATE UNIQUE INDEX uq_bind_vehicle_active ON device_vehicle_bind (vehicle_id) WHERE unbound_at IS NULL;
```

---

### 6. `geo_zone` — 地理围栏与区域

```sql
CREATE TABLE geo_zone (
  id          BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        VARCHAR(100) NOT NULL,                  -- 区域名称
  zone_type   VARCHAR(30)  NOT NULL,                  -- 类型：见下方枚举说明
  coordinates JSONB        NOT NULL,                  -- GCJ-02坐标数组 [[lng,lat],...]
  speed_limit SMALLINT,                               -- 区域限速(km/h)，NULL=使用全局限速
  dwell_min   SMALLINT,                               -- 最短驻留时长(分钟)，用于装卸料区判定
  is_enabled  BOOLEAN      NOT NULL DEFAULT TRUE,
  extra       JSONB,                                  -- 扩展配置，备用
  notes       TEXT,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_geo_zone_type    ON geo_zone (zone_type);
CREATE INDEX idx_geo_zone_enabled ON geo_zone (is_enabled);
CREATE INDEX idx_geo_zone_coords  ON geo_zone USING GIN (coordinates); -- JSONB GIN 索引

CREATE TRIGGER trg_geo_zone_updated_at
  BEFORE UPDATE ON geo_zone
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

**`zone_type` 枚举说明**

| 值 | 含义 |
| --- | --- |
| `loading` | 装料区 |
| `unloading` | 卸料区 |
| `restricted` | 限行区域 |
| `sharp_curve` | 急弯（会车提醒） |
| `single_bridge` | 单边桥/窄路（调度） |
| `speed_zone` | 仅限速区（无其它业务） |

---

### 7. `operation_ban` — 禁止运营时段规则

> 后台按区域 + 时段配置禁运规则，对应 `event.event_type = 'ban_violation'`。`zone_id` 为 NULL 表示全局禁运（不限区域）。

```sql
CREATE TABLE operation_ban (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  zone_id    BIGINT,                                  -- FK geo_zone.id，NULL=全局禁运
  start_time TIME        NOT NULL,                    -- 禁运开始时刻（本地时间）
  end_time   TIME        NOT NULL,                    -- 禁运结束时刻（本地时间）
  weekdays   SMALLINT[]  NOT NULL DEFAULT '{1,2,3,4,5,6,7}', -- 生效星期（1=周一…7=周日）
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
```

> **注意**：跨零点时段（如 22:00–06:00）的判断需在应用层处理跨日逻辑，建议封装统一工具函数。

---

### 8. `business_config` — 业务运营参数

> 全局单行（`id=1`），运营人员可在后台调整。

```sql
CREATE TABLE business_config (
  id                  BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  global_speed_limit  SMALLINT    NOT NULL DEFAULT 80,   -- 全局限速(km/h)
  park_threshold_min  SMALLINT    NOT NULL DEFAULT 10,   -- 停车/idle 判定阈值(分钟)；100m 半径内停留超此值 → idle
  loading_dwell_s     INT         NOT NULL DEFAULT 300,  -- 装料最短驻留(秒)；≥ 此值确认为 loading（V007 由 loading_dwell_min 重命名，原值×60）
  unloading_dwell_s   INT         NOT NULL DEFAULT 300,  -- 卸料最短驻留(秒)；≥ 此值确认为 unloading（V007 由 unloading_dwell_min 重命名，原值×60）
  alert_cooldown_s    SMALLINT    NOT NULL DEFAULT 10,   -- 告警防抖间隔(秒)
  hb_timeout_s        SMALLINT    NOT NULL DEFAULT 90,   -- 心跳超时判定(秒)
  weather_city        VARCHAR(50) NOT NULL DEFAULT 'Nanjing', -- 天气查询城市
  weather_cache_min   SMALLINT    NOT NULL DEFAULT 30,   -- 天气缓存时长(分钟)
  map_center_lng      DOUBLE PRECISION NOT NULL DEFAULT 109.4753, -- 地图默认中心经度 GCJ-02
  map_center_lat      DOUBLE PRECISION NOT NULL DEFAULT 30.2832,  -- 地图默认中心纬度 GCJ-02
  transport_timeout_min INT        NOT NULL DEFAULT 30,  -- 运输超时阈值（分钟）；0=禁用；超时后段类型改为 unknown
  segment_buffer_min  SMALLINT    NOT NULL DEFAULT 3,    -- 运输段展示缓冲（分钟）；查询时额外取 started_at-N 到 ended_at+N 的点（V007 新增）
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 初始化默认行
INSERT INTO business_config DEFAULT VALUES;

-- 迁移历史（Alembic）
-- V004: ADD COLUMN map_center_lng, map_center_lat
-- V005: ADD COLUMN segment_type ON track_segment
-- V006: ADD COLUMN transport_timeout_min
-- V007: loading_dwell_min→loading_dwell_s(×60), unloading_dwell_min→unloading_dwell_s(×60),
--        ADD segment_buffer_min, work_state_t ADD VALUE 'idle',
--        location_point DROP COLUMN segment_id, DROP INDEX idx_lp_segment

CREATE TRIGGER trg_business_config_updated_at
  BEFORE UPDATE ON business_config
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

### 9. `location_point` — 高频定位点

> 1 秒/次，数据量大。按 `recorded_at` 月份声明式分区；时序列使用 **BRIN 索引**替代 B-tree，体积降低约 3 个数量级。

```sql
CREATE TABLE location_point (
  id          BIGINT         GENERATED ALWAYS AS IDENTITY,
  device_id   BIGINT         NOT NULL,               -- FK device.id
  vehicle_id  BIGINT,                                -- FK vehicle.id，绑定后写入
  -- segment_id 列已在 V007 迁移中删除（v1.2.0）
  -- 段的点集改由 (vehicle_id, recorded_at BETWEEN started_at AND ended_at) 时间范围查询
  recorded_at TIMESTAMPTZ    NOT NULL,               -- 定位时间（设备端 GPS 时间戳）
  lat         NUMERIC(10,7)  NOT NULL,               -- 纬度 WGS-84
  lng         NUMERIC(10,7)  NOT NULL,               -- 经度 WGS-84
  speed       NUMERIC(6,2),                          -- 速度(km/h)
  altitude    NUMERIC(8,2),                          -- 海拔(m)
  loc_type    loc_type_t     NOT NULL DEFAULT 'gps', -- 定位类型
  created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
  PRIMARY KEY (id, recorded_at)                      -- 分区表主键须含分区键
) PARTITION BY RANGE (recorded_at);

-- B-tree 复合索引（设备/车辆维度精确范围查询）
CREATE INDEX idx_lp_device_time  ON location_point (device_id,  recorded_at);
CREATE INDEX idx_lp_vehicle_time ON location_point (vehicle_id, recorded_at);
-- idx_lp_segment 已在 V007 迁移中删除（随 segment_id 列一同移除）

-- BRIN 索引：纯时间顺序扫描，体积约为 B-tree 的 1/1000
CREATE INDEX idx_lp_time_brin ON location_point USING BRIN (recorded_at);
```

**月分区示例**

```sql
-- 手动建分区，或通过 pg_partman 扩展自动管理
CREATE TABLE location_point_2025_01 PARTITION OF location_point
  FOR VALUES FROM ('2025-01-01 00:00:00+00') TO ('2025-02-01 00:00:00+00');

CREATE TABLE location_point_2025_02 PARTITION OF location_point
  FOR VALUES FROM ('2025-02-01 00:00:00+00') TO ('2025-03-01 00:00:00+00');
```

---

### 10. `track_segment` — 轨迹段

```sql
CREATE TABLE track_segment (
  id           BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id    BIGINT         NOT NULL,               -- FK device.id
  vehicle_id   BIGINT,                                -- FK vehicle.id
  started_at   TIMESTAMPTZ    NOT NULL,               -- 段开始时间（装/卸料段回溯至 zone_entry_at）
  ended_at     TIMESTAMPTZ,                           -- 段结束时间，NULL=实时开放中
  start_lat    NUMERIC(10,7),                         -- 起点纬度 WGS-84
  start_lng    NUMERIC(10,7),                         -- 起点经度 WGS-84
  end_lat      NUMERIC(10,7),                         -- 终点纬度 WGS-84
  end_lng      NUMERIC(10,7),                         -- 终点经度 WGS-84
  point_count  INT            NOT NULL DEFAULT 0,     -- 段内定位点数（时间范围内的总点数）
  segment_type VARCHAR(20),                           -- 段类型，见下方说明
  label        VARCHAR(100),
  created_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- segment_type 取值说明（v1.2.0 扩展）：
--   NULL              : 实时开放中尚未确认类型（transport 段确认前的过渡状态）
--   'loading'         : 装料中；车辆在取土围栏内停留 ≥ loading_dwell_s 秒
--   'unloading'       : 卸料中；车辆在弃土围栏内停留 ≥ unloading_dwell_s 秒
--   'transport_loaded': 运料中；从装料区离开到进入卸料区（未超时）
--   'transport_empty' : 空载中；从卸料区离开到进入装料区（未超时）
--   'unknown'         : 未知轨迹；运输超时/无法分类的行驶段/连接初期
--   'idle'            : 停车闲置；不在装/卸料区的长时停车（默认隐藏）
--
-- 查询段内定位点：
--   SELECT * FROM location_point
--   WHERE vehicle_id = $1 AND recorded_at BETWEEN started_at AND ended_at
--
-- 查询 transport 段定位点（含 3min 展示缓冲）：
--   WHERE vehicle_id = $1
--     AND recorded_at BETWEEN (started_at - segment_buffer_min * INTERVAL '1 min')
--                         AND (ended_at   + segment_buffer_min * INTERVAL '1 min')

CREATE INDEX idx_seg_device_start  ON track_segment (device_id,  started_at);
CREATE INDEX idx_seg_vehicle_start ON track_segment (vehicle_id, started_at);

CREATE TRIGGER trg_track_segment_updated_at
  BEFORE UPDATE ON track_segment
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

### 11. `work_session` — 作业状态会话

```sql
CREATE TABLE work_session (
  id         BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  vehicle_id BIGINT       NOT NULL,                  -- FK vehicle.id
  state      work_state_t NOT NULL,                  -- 作业状态
  zone_id    BIGINT,                                 -- FK geo_zone.id，触发状态的区域
  started_at TIMESTAMPTZ  NOT NULL,                  -- 状态开始时间
  ended_at   TIMESTAMPTZ,                            -- 状态结束时间，NULL=进行中
  duration_s INT,                                    -- 持续秒数，关闭时写入
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ws_vehicle_start ON work_session (vehicle_id, started_at);
CREATE INDEX idx_ws_zone          ON work_session (zone_id);
```

---

### 12. `event` — 统一事件与告警留痕

```sql
CREATE TABLE event (
  id          BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id   BIGINT,                                -- FK device.id
  vehicle_id  BIGINT,                                -- FK vehicle.id
  event_type  VARCHAR(40)    NOT NULL,               -- 事件类型，见下方枚举说明
  severity    SMALLINT       NOT NULL DEFAULT 2,     -- 1=信息 2=警告 3=告警
  zone_id     BIGINT,                                -- FK geo_zone.id，关联区域
  ban_id      BIGINT,                                -- FK operation_ban.id，关联禁运规则
  lat         NUMERIC(10,7),                         -- 事件发生位置纬度 WGS-84
  lng         NUMERIC(10,7),                         -- 事件发生位置经度 WGS-84
  speed       NUMERIC(6,2),                          -- 事件发生时速度(km/h)
  cmd_sent    VARCHAR(10),                           -- 下发的指令，如 ws/wa/vs
  detail      JSONB,                                 -- 扩展细节，如限速值、围栏名等
  occurred_at TIMESTAMPTZ    NOT NULL,               -- 事件发生时间
  created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_event_vehicle_time ON event (vehicle_id, occurred_at);
CREATE INDEX idx_event_device_time  ON event (device_id,  occurred_at);
CREATE INDEX idx_event_type         ON event (event_type);
CREATE INDEX idx_event_zone         ON event (zone_id);
CREATE INDEX idx_event_detail_gin   ON event USING GIN (detail); -- JSONB GIN 索引
```

**`event_type` 枚举说明**

| 值 | 含义 |
| --- | --- |
| `overspeed` | 超速告警 |
| `geofence_violation` | 越界告警 |
| `oncoming_warn` | 急弯会车提醒 |
| `dispatch` | 单边桥/窄路调度 |
| `ban_violation` | 禁止运营违规（关联 `operation_ban`） |
| `zone_entry` | 进入区域 |
| `zone_exit` | 离开区域 |
| `device_offline` | 设备离线 |
| `unreported_exit` | 私自离开未报备 |

---

### 13. `command_log` — 下行指令记录

```sql
CREATE TABLE command_log (
  id           BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id    BIGINT,                                -- FK device.id
  vehicle_id   BIGINT,                                -- FK vehicle.id
  cmd          VARCHAR(20)  NOT NULL,                 -- 指令内容，如 ws/wa/vs/gm
  source       cmd_source_t NOT NULL DEFAULT 'auto',  -- 触发来源
  operator_id  BIGINT,                                -- FK app_user.id，手动下发时记录
  event_id     BIGINT,                                -- FK event.id，关联触发事件
  speed_kmh    NUMERIC(8,2),                          -- 下发时车速(km/h)（V003 迁移新增）
  is_delivered BOOLEAN      NOT NULL DEFAULT FALSE,   -- 是否成功发送到设备
  sent_at      TIMESTAMPTZ  NOT NULL,                 -- 发送时间
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cmd_device_time  ON command_log (device_id,  sent_at);
CREATE INDEX idx_cmd_vehicle_time ON command_log (vehicle_id, sent_at);
```

---

### 14. `app_user` — 用户与角色

> 表名使用 `app_user` 避免与 PostgreSQL 内置保留字 `user` 冲突。  
> `fleet_id` 仅对 `fleet_captain` 角色有意义（绑定所属车队）；`manager` 与 `terminal` 置 `NULL`。

```sql
CREATE TABLE app_user (
  id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username      VARCHAR(50) NOT NULL,
  password_hash TEXT        NOT NULL,                  -- bcrypt/Argon2id 哈希，禁止 SHA-256
  role          user_role_t NOT NULL DEFAULT 'fleet_captain',
  fleet_id      BIGINT,                                -- FK fleet.id；fleet_captain 必填，其他角色为 NULL
  is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_username UNIQUE (username),
  -- 约束：fleet_captain 必须绑定车队
  CONSTRAINT chk_fleet_captain_fleet
    CHECK (role != 'fleet_captain' OR fleet_id IS NOT NULL)
);

-- 部分索引：仅对活跃用户建索引
CREATE INDEX idx_user_active      ON app_user (username)  WHERE deleted_at IS NULL;
CREATE INDEX idx_user_fleet       ON app_user (fleet_id)  WHERE deleted_at IS NULL;

CREATE TRIGGER trg_app_user_updated_at
  BEFORE UPDATE ON app_user
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

### 15. `sys_config` — 系统/部署参数

> 键值对形式，仅运维修改，不与业务配置混用。字段名由 `key` 改为 `config_key`，避免与 SQL 保留字歧义。

```sql
CREATE TABLE sys_config (
  config_key  VARCHAR(60)  NOT NULL PRIMARY KEY,
  value       TEXT         NOT NULL,
  description VARCHAR(200),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 初始化示例参数
INSERT INTO sys_config (config_key, value, description) VALUES
  ('tcp_port',          '9000',  'TCP 监听端口'),
  ('http_port',         '8080',  'HTTP 管理界面端口'),
  ('gps_filter_enable', '1',     'GPS卡尔曼滤波开关 1=启用 0=关闭'),
  ('gps_filter_alpha',  '0.2',   'GPS卡尔曼滤波系数 α，范围 0~1');

CREATE TRIGGER trg_sys_config_updated_at
  BEFORE UPDATE ON sys_config
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 表关系速览

```
fleet
 ├─ vehicle.fleet_id
 └─ app_user.fleet_id  (fleet_captain 专用)

app_user
 └─ command_log.operator_id

vehicle ──────────────────────────────────────┐
 ├─ device_vehicle_bind.vehicle_id            │
 ├─ location_point.vehicle_id                 │
 ├─ track_segment.vehicle_id                  │
 ├─ work_session.vehicle_id                   │
 ├─ event.vehicle_id                          │
 └─ command_log.vehicle_id                    │
                                              │
device ───────────────────────────────────────┤
 ├─ device_vehicle_bind.device_id             │
 ├─ location_point.device_id                  │
 ├─ track_segment.device_id                   │
 ├─ event.device_id                           │
 └─ command_log.device_id                     │
                                              │
driver                                        │
 ├─ fleet.id (fleet_id)                       │
 └─ device_vehicle_bind.driver_id             │
                                              │
geo_zone                                      │
 ├─ work_session.zone_id                      │
 ├─ event.zone_id                             │
 └─ operation_ban.zone_id                     │
                                              │
operation_ban                                 │
 └─ event.ban_id                              │
                                              │
track_segment                                 │
 └─ （v1.2.0 已移除 location_point.segment_id；段的点集通过时间范围查询推导）
                                              │
event                                         │
 └─ command_log.event_id                      │
```

---

## 数据库迁移版本历史

| 版本 | 文件 | 变更内容 |
|------|------|----------|
| V001 | `V001__init_schema.py` | 初始建表：全部基础表 + 触发器 + 索引 |
| V002 | `V002__add_vehicle_driver_name.py` | `vehicle` 表新增 `driver_name VARCHAR(50)` |
| V003 | `V003__command_log_speed.py` | `command_log` 表新增 `speed_kmh NUMERIC(8,2)` |

| V004 | `V004__add_map_center.py` | `business_config` 新增 `map_center_lng`、`map_center_lat` |
| V005 | `V005__add_segment_type.py` | `track_segment` 新增 `segment_type VARCHAR(20)` |
| V006 | `V006__add_transport_timeout.py` | `business_config` 新增 `transport_timeout_min INT` |
| V007 | `V007__segment_v2.py` | **轨迹分段重构 v1.2.0**：`location_point` 删除 `segment_id` 列及索引；`business_config` 字段 `loading_dwell_min`→`loading_dwell_s`（值×60）、`unloading_dwell_min`→`unloading_dwell_s`（值×60），新增 `segment_buffer_min SMALLINT DEFAULT 3`；`work_state_t` 枚举新增 `idle` |
> 执行 `alembic upgrade head` 应用全部迁移。新增字段均使用 `IF NOT EXISTS`，可安全重复执行。

---

## 坐标系使用约定

| 位置 | 坐标系 | 说明 |
|------|--------|------|
| `location_point.lat/lng` | **WGS-84** | 设备 GPS 原始上报；LBS 基站定位亦为 WGS-84 |
| `track_segment.start_lat/lng`、`end_lat/lng` | **WGS-84** | 数据库存储原始坐标 |
| `geo_zone.coordinates` | **GCJ-02** | 前端高德地图绘制后直接存储 |
| API 返回给前端的坐标 | **GCJ-02** | 路由层调用 `wgs84_to_gcj02()`（`geofence_service`）后返回 |

> **约定**：坐标转换统一在 HTTP 路由层（`router_track_segments.py`）执行，DB 中始终存 WGS-84，不做双写。

---

## 待补充 / 后续优化

- **`location_point` 自动分区**：推荐引入 `pg_partman` 扩展，自动按月创建分区并制定冷热归档策略，替代手工 `CREATE TABLE ... PARTITION OF`。
- **`location_point` VACUUM 调优**：高频写入会产生大量死元组，建议对该表设置表级参数 `autovacuum_vacuum_scale_factor = 0.01`，加快 autovacuum 触发频率。
- **TimescaleDB（可选扩展）**：设备规模 ≥ 100 台时，可将 `location_point` 转为 TimescaleDB hypertable，获得自动分块、连续聚合（Continuous Aggregates）与数据保留策略，报表查询可提速 10x+。
- **PostGIS（可选扩展）**：围栏数量增加时，可将 `geo_zone.coordinates` 由 `JSONB` 迁移为 `GEOMETRY(POLYGON, 4326)` + 空间索引，把点在多边形判定下推至数据库，消除应用层循环开销。注意 GCJ-02 坐标需先在应用层转换为 WGS-84 再入库。
- **大屏设计（待完善）**：大屏查看权限已在角色权限速览中预留（`manager` 全部，`fleet_captain` 仅本车队），前端实现细节待后续补充。
- **`fleet_captain` 围栏权限细化**：当前允许车队长配置围栏，如需限制为"仅能查看、不能新建/修改"，需在应用层接口加角色判断，数据库层不做额外约束。
- **Session 存储**：Session 已通过 Redis `session:{uuid}` 存储（TTL 24 小时，每次请求滑动续期），天然支持多实例共享与强制踢出；详见 `ARCHITECTURE.md §9`。
- **管理员二次验证**：`manager` 执行高危系统操作时需二次输入密码，由服务层在对应接口前置校验，无需额外数据库字段。
- **密码哈希升级**：若旧数据存有 SHA-256 哈希，需在用户下次登录时触发透明升级（验证旧哈希后重新用 bcrypt 存储）。
- **`operation_ban` 跨零点逻辑**：`start_time > end_time` 时（如 22:00–06:00）需在服务层封装统一判断函数处理跨日情形。
- **索引调优**：根据实际查询模式（大屏实时、历史轨迹回放、统计报表）补充复合索引，可通过 `pg_stat_statements` + `auto_explain` 辅助定位慢查询。
- **迁移版本管理**：建议引入版本化 SQL 脚本（如 Flyway `V1__init.sql` 或 Liquibase）管理 schema 变更，避免手工执行 DDL。
