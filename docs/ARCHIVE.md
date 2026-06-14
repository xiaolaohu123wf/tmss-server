# TMSS 数据归档规范

> **文档版本**：v1.4.2  
> **适用系统**：Truck Monitoring System Simplify（TMSS）  
> **数据库**：PostgreSQL 16+，库名 `tmss_db`  
> **坐标系约定**：`location_point` 存 WGS-84 原始坐标；`geo_zone`、`event` 位置字段存 GCJ-02；归档时**不转换坐标系**，由读取方按字段备注自行处理。

---

## 目录

1. [归档范围](#1-归档范围)
2. [数据分级与冷热策略](#2-数据分级与冷热策略)
3. [各表归档细则](#3-各表归档细则)
4. [归档触发条件与周期](#4-归档触发条件与周期)
5. [导出格式规范](#5-导出格式规范)
6. [文件命名与目录结构](#6-文件命名与目录结构)
7. [完整性校验清单](#7-完整性校验清单)

---

## 1. 归档范围

**纳入归档**的表：

| 表名 | 数据特征 |
|------|---------|
| `location_point` | 1 秒/次高频定位，主要归档对象，按月分区 |
| `track_segment` | 行程分段，与定位点联动归档 |
| `work_session` | 作业状态会话，统计基础 |
| `event` | 告警/违规事件，合规留痕核心 |
| `command_log` | 下行指令记录 |
| `device_vehicle_bind` | 绑定/解绑历史，人员与设备追溯 |

**关联快照**（归档时附带，保证孤立归档文件可读）：

| 表名 | 快照必要性 |
|------|-----------|
| `vehicle` | 车牌、车型等名称不存于流水表，归档时需快照当前状态 |
| `device` | IMEI、固件版本，供设备溯源 |
| `driver` | 驾驶员姓名与证号 |
| `fleet` | 车队名称 |
| `geo_zone` | 围栏坐标与名称，供事件回溯 |

**不归档**的表：

| 表名 | 原因 |
|------|------|
| `app_user` | 账号安全数据（含密码哈希），不写入归档文件 |
| `business_config` | 运营参数，无时序价值，保留在主库即可 |
| `operation_ban` | 规则配置，与 `business_config` 同类 |
| `sys_config` | 系统参数，不归档 |

---

## 2. 数据分级与冷热策略

系统数据按访问频率和业务时效分为三个层级：

| 层级 | 保留窗口 | 存储介质 | 典型访问场景 |
|------|---------|---------|------------|
| **HOT**（在线热数据） | 近 3 个月 | 主库分区表（PostgreSQL） | 实时查询、SSE 推送、大屏展示 |
| **WARM**（近期归档） | 3 个月 ~ 12 个月 | 归档库或只读副本 | 偶发历史轨迹查询、月度统计报表 |
| **COLD**（冷归档） | 12 个月以上 | 对象存储（NAS / MinIO / OSS） | 合规审计、年度统计，按需解压 |

**分级依据**

| 维度 | HOT | WARM | COLD |
|------|-----|------|------|
| 主库访问频率 | 高（每分钟） | 低（每周以下） | 极低（按需） |
| 数据完整性要求 | 完整行 + 索引 | 完整行（无索引加速） | 行级压缩文件 |
| 恢复时效要求 | 毫秒级 | 秒级 | 分钟级（解压） |

---

## 3. 各表归档细则

### 3.1 `location_point` — 高频定位点

> **最大体量表**，每台设备约 86,400 行/天。归档驱动整个归档流程的节奏。

**归档字段（完整列集）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键（分区子键） |
| `device_id` | BIGINT | 设备 ID（关联 `device.id`） |
| `vehicle_id` | BIGINT \| NULL | 车辆 ID（绑定时写入） |
| `recorded_at_cst` | TEXT | 定位时间，CST（UTC+8），ISO 8601 格式 |
| `lat` | NUMERIC(10,7) | 纬度，**WGS-84** |
| `lng` | NUMERIC(10,7) | 经度，**WGS-84** |
| `speed` | NUMERIC(6,2) \| NULL | 速度（km/h） |
| `altitude` | NUMERIC(8,2) \| NULL | 海拔（m） |
| `loc_type` | TEXT | 定位类型：`gps` / `lbs` |
| `created_at_cst` | TEXT | 服务端入库时间，CST（UTC+8） |

> **时区处理**：数据库内以 UTC 存储，导出时统一转换为 CST（UTC+8），列名后缀 `_cst` 标注，保持存储与导出的明确区分。

**归档粒度**：以**自然月**为最小单位（与分区表对齐）。

**归档条件**：分区月份结束 **30 天后**（即距今超过约 **120 天**）进入 WARM，超过 **365 天**进入 COLD。

**CSV 数据示例**

```csv
id,device_id,vehicle_id,recorded_at_cst,lat,lng,speed,altitude,loc_type,created_at_cst
1001,12,5,2025-01-15T08:23:11+08:00,30.2843210,109.4762350,42.50,312.30,gps,2025-01-15T08:23:12+08:00
1002,12,5,2025-01-15T08:23:12+08:00,30.2844100,109.4763200,43.20,312.40,gps,2025-01-15T08:23:13+08:00
1003,15,,2025-01-15T08:23:13+08:00,30.2850000,109.4770000,0.00,310.00,lbs,2025-01-15T08:23:14+08:00
```

> 第 3 行 `vehicle_id` 为空（设备未绑定车辆）；`speed=0.00` 表示设备静止；`loc_type=lbs` 表示 GPS 失锁，由基站定位兜底。

---

### 3.2 `track_segment` — 轨迹段

**归档字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `device_id` | BIGINT | 设备 ID |
| `vehicle_id` | BIGINT \| NULL | 车辆 ID |
| `started_at_cst` | TEXT | 段开始时间，CST |
| `ended_at_cst` | TEXT \| NULL | 段结束时间，NULL 表示实时开放中（**归档前须确认已关闭**） |
| `start_lat` / `start_lng` | NUMERIC(10,7) | 起点坐标，**WGS-84** |
| `end_lat` / `end_lng` | NUMERIC(10,7) | 终点坐标，**WGS-84** |
| `point_count` | INT | 段内定位点总数 |
| `segment_type` | TEXT | 段类型（见下表） |
| `label` | TEXT \| NULL | 人工标注备注 |
| `created_at_cst` | TEXT | 创建时间，CST |
| `updated_at_cst` | TEXT | 最后更新时间，CST |

**`segment_type` 值域**

| 值 | 含义 |
|----|------|
| `loading` | 装料段 |
| `unloading` | 卸料段 |
| `transport_loaded` | 重载运输段 |
| `transport_empty` | 空载运输段 |
| `unknown` | 未知（运输超时或无法分类） |
| `idle` | 停车闲置段 |
| NULL | 实时开放中，**不允许归档** |

**归档条件**：`ended_at IS NOT NULL` 且 `ended_at` 距今超过 **90 天**。

**CSV 数据示例**

```csv
id,device_id,vehicle_id,started_at_cst,ended_at_cst,start_lat,start_lng,end_lat,end_lng,point_count,segment_type,label,created_at_cst,updated_at_cst
301,12,5,2025-01-15T07:10:00+08:00,2025-01-15T07:28:45+08:00,30.2801000,109.4700000,30.3120000,109.5300000,1125,transport_loaded,,2025-01-15T07:10:01+08:00,2025-01-15T07:28:46+08:00
302,12,5,2025-01-15T07:28:45+08:00,2025-01-15T07:45:00+08:00,30.3120000,109.5300000,30.3125000,109.5302000,975,unloading,,2025-01-15T07:28:45+08:00,2025-01-15T07:45:01+08:00
```

---

### 3.3 `work_session` — 作业状态会话

**归档字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `vehicle_id` | BIGINT | 车辆 ID |
| `state` | TEXT | 作业状态（`loading` / `unloading` / `transport_loaded` / `transport_empty` / `unknown` / `idle`） |
| `zone_id` | BIGINT \| NULL | 触发状态的围栏 ID |
| `started_at_cst` | TEXT | 状态开始时间，CST |
| `ended_at_cst` | TEXT \| NULL | 状态结束时间，NULL=进行中（**归档前须确认已结束**） |
| `duration_s` | INT \| NULL | 持续秒数 |
| `created_at_cst` | TEXT | 创建时间，CST |

**归档条件**：`ended_at IS NOT NULL` 且 `started_at` 距今超过 **90 天**。

**CSV 数据示例**

```csv
id,vehicle_id,state,zone_id,started_at_cst,ended_at_cst,duration_s,created_at_cst
501,5,loading,3,2025-01-15T07:10:00+08:00,2025-01-15T07:15:30+08:00,330,2025-01-15T07:10:01+08:00
502,5,transport_loaded,,2025-01-15T07:15:30+08:00,2025-01-15T07:28:45+08:00,795,2025-01-15T07:15:31+08:00
503,5,unloading,7,2025-01-15T07:28:45+08:00,2025-01-15T07:33:20+08:00,275,2025-01-15T07:28:46+08:00
```

---

### 3.4 `event` — 告警与事件

> 合规留痕核心表，**最低保留 3 年**，任何清理操作需提前确认归档文件完整。

**归档字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `device_id` | BIGINT \| NULL | 设备 ID |
| `vehicle_id` | BIGINT \| NULL | 车辆 ID |
| `event_type` | TEXT | 事件类型（见下表） |
| `severity` | SMALLINT | 严重程度：1=信息 2=警告 3=告警 |
| `zone_id` | BIGINT \| NULL | 关联围栏 ID |
| `ban_id` | BIGINT \| NULL | 关联禁运规则 ID |
| `lat` / `lng` | NUMERIC(10,7) | 事件发生坐标，**WGS-84** |
| `speed` | NUMERIC(6,2) \| NULL | 事件发生时速度（km/h） |
| `cmd_sent` | TEXT \| NULL | 已下发指令（如 `ws` / `wa` / `vs`） |
| `detail` | JSON object | 扩展细节（限速值、围栏名等） |
| `occurred_at_cst` | TEXT | 事件发生时间，CST |
| `created_at_cst` | TEXT | 入库时间，CST |

**`event_type` 值域**

| 值 | 含义 | 严重程度 |
|----|------|---------|
| `overspeed` | 超速告警 | 3 |
| `geofence_violation` | 越界告警 | 3 |
| `ban_violation` | 禁止运营违规 | 3 |
| `unreported_exit` | 私自离开未报备 | 3 |
| `oncoming_warn` | 急弯会车提醒 | 2 |
| `dispatch` | 单边桥/窄路调度 | 2 |
| `device_offline` | 设备离线 | 2 |
| `zone_entry` | 进入区域 | 1 |
| `zone_exit` | 离开区域 | 1 |

**归档条件**：`occurred_at` 距今超过 **90 天**（`severity=3` 的记录保留 3 年后可转 COLD）。

**NDJSON 数据示例**（每行一条记录）

```json
{"id":2045,"device_id":12,"vehicle_id":5,"event_type":"overspeed","severity":3,"zone_id":null,"ban_id":null,"lat":30.2843210,"lng":109.4762350,"speed":92.40,"cmd_sent":"ws","detail":{"speed_limit":80,"zone_name":null},"occurred_at_cst":"2025-01-15T08:23:11+08:00","created_at_cst":"2025-01-15T08:23:12+08:00"}
{"id":2046,"device_id":15,"vehicle_id":8,"event_type":"geofence_violation","severity":3,"zone_id":4,"ban_id":null,"lat":30.3011500,"lng":109.4890200,"speed":35.10,"cmd_sent":"wa","detail":{"zone_name":"限行区域A","entry_side":"north"},"occurred_at_cst":"2025-01-15T09:05:44+08:00","created_at_cst":"2025-01-15T09:05:45+08:00"}
{"id":2047,"device_id":12,"vehicle_id":5,"event_type":"zone_entry","severity":1,"zone_id":3,"ban_id":null,"lat":30.2801000,"lng":109.4700000,"speed":8.20,"cmd_sent":null,"detail":{"zone_name":"取土区1"},"occurred_at_cst":"2025-01-15T09:10:00+08:00","created_at_cst":"2025-01-15T09:10:01+08:00"}
```

---

### 3.5 `command_log` — 下行指令记录

**归档字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `device_id` | BIGINT \| NULL | 设备 ID |
| `vehicle_id` | BIGINT \| NULL | 车辆 ID |
| `cmd` | TEXT | 指令内容（如 `ws` / `wa` / `gm` / `vs`） |
| `source` | TEXT | 触发来源：`auto` / `manual` |
| `operator_id` | BIGINT \| NULL | 手动下发时操作人用户 ID |
| `event_id` | BIGINT \| NULL | 关联触发事件 ID |
| `speed_kmh` | NUMERIC(8,2) \| NULL | 下发时车速（km/h） |
| `is_delivered` | BOOLEAN | 是否成功送达设备 |
| `sent_at_cst` | TEXT | 发送时间，CST |
| `created_at_cst` | TEXT | 入库时间，CST |

**归档条件**：`sent_at` 距今超过 **90 天**。

**CSV 数据示例**

```csv
id,device_id,vehicle_id,cmd,source,operator_id,event_id,speed_kmh,is_delivered,sent_at_cst,created_at_cst
701,12,5,ws,auto,,2045,92.40,true,2025-01-15T08:23:11+08:00,2025-01-15T08:23:11+08:00
702,15,8,wa,auto,,2046,35.10,true,2025-01-15T09:05:44+08:00,2025-01-15T09:05:44+08:00
703,12,5,gm,manual,1,,0.00,true,2025-01-15T06:58:30+08:00,2025-01-15T06:58:30+08:00
```

---

### 3.6 `device_vehicle_bind` — 绑定历史

**归档字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `device_id` | BIGINT | 设备 ID |
| `vehicle_id` | BIGINT | 车辆 ID |
| `driver_id` | BIGINT \| NULL | 驾驶员 ID |
| `bound_at_cst` | TEXT | 绑定时间，CST |
| `unbound_at_cst` | TEXT \| NULL | 解绑时间，NULL=当前仍绑定（**归档前须确认已解绑**） |
| `operator` | TEXT \| NULL | 操作人用户名（冗余存储，归档后可独立读取） |
| `created_at_cst` | TEXT | 创建时间，CST |

**归档条件**：`unbound_at IS NOT NULL` 且 `unbound_at` 距今超过 **365 天**。

**CSV 数据示例**

```csv
id,device_id,vehicle_id,driver_id,bound_at_cst,unbound_at_cst,operator,created_at_cst
101,12,5,3,2024-03-01T09:00:00+08:00,2024-12-31T18:00:00+08:00,admin,2024-03-01T09:00:01+08:00
102,15,8,,2024-05-10T08:30:00+08:00,2024-11-20T17:45:00+08:00,admin,2024-05-10T08:30:01+08:00
```

---

### 3.7 关联快照表

> 快照在**每次归档执行时一并导出**，确保归档包自包含、可独立读取。

| 快照表 | 导出内容 | 排除字段 |
|--------|---------|---------|
| `fleet` | 全量（含软删除，保留 `deleted_at`） | 无 |
| `vehicle` | 全量（含软删除） | 无 |
| `device` | 全量（含软删除） | 无 |
| `driver` | 全量（含软删除） | 无 |
| `geo_zone` | 全量 | 无 |
| `app_user` | **不归档**（账号安全数据，含密码哈希） | — |

**快照 CSV 示例（`vehicle`）**

```csv
id,fleet_id,license_plate,vehicle_type,load_capacity,driver_name,notes,deleted_at,created_at_cst,updated_at_cst
5,2,渝A12345,truck,30.00,张三,,2025-03-01T10:00:00+08:00,2025-01-15T08:00:00+08:00
8,2,渝A67890,loader,,李四,,2025-03-01T10:00:00+08:00,2025-01-15T08:00:00+08:00
```

---

## 4. 归档触发条件与周期

### 4.1 定期触发（推荐）

| 触发周期 | 执行内容 |
|---------|---------|
| **每月 1 日凌晨 02:00** | 归档上上月的 `location_point` 分区（例：3 月 1 日归档 1 月分区） |
| **每月 1 日凌晨 02:30** | 归档上上月区间的 `track_segment`、`work_session`、`event`、`command_log` |
| **每季度末最后一天** | 归档超过 365 天的 `device_vehicle_bind` 解绑历史；更新所有关联快照 |
| **每年 1 月 1 日** | 将超过 12 个月的 WARM 归档转移至 COLD 存储 |

> 推迟两个月归档（而非上月立即归档）是为保留近期历史轨迹查询窗口，避免业务方查询上月数据时找不到记录。可根据实际需求缩短至 **60 天**。

### 4.2 容量触发

当 `location_point` 分区总体积超过 **50 GB**，或单分区超过 **5 GB** 时，立即触发归档，不等待月度定时任务。

分区体积查询：

```sql
SELECT
  c.relname                                             AS partition_name,
  pg_size_pretty(pg_total_relation_size(c.oid))         AS total_size
FROM pg_class c
JOIN pg_inherits i ON i.inhrelid = c.oid
JOIN pg_class p   ON p.oid = i.inhparent
WHERE p.relname = 'location_point'
ORDER BY pg_total_relation_size(c.oid) DESC;
```

### 4.3 手动触发

运维人员可在任何时候手动执行归档，建议在**业务低峰期**（凌晨 00:00–06:00）进行，避免影响在线查询。

---

## 5. 导出格式规范

### 5.1 格式选型

| 格式 | 适用表 | 优点 | 注意事项 |
|------|-------|------|---------|
| **CSV（UTF-8，带标题行）** | `location_point`、`track_segment`、`work_session`、`command_log`、`device_vehicle_bind`、所有快照 | 通用性强，任意工具可读 | JSONB 列需序列化为字符串；NUMERIC 精度注意引号处理 |
| **NDJSON**（每行一个 JSON 对象） | `event` | 保留 `detail` JSONB 原始嵌套结构，字段可扩展 | 体积略大于 CSV |
| **Parquet**（可选，长期分析用） | `location_point`（超大归档） | 列式存储，压缩比高，Spark / DuckDB 原生支持 | 需额外工具转换 |

### 5.2 CSV 规范

```
编码          UTF-8，无 BOM
分隔符        英文逗号 ,
字符串引用    仅在字段包含逗号、换行或引号时加双引号
NULL 值       空字符串（不写 \N 或 NULL 字面量）
时间戳格式    ISO 8601，含时区偏移，如 2025-01-15T08:30:00+08:00
布尔值        true / false（小写）
ENUM 值       原始字符串（如 gps、loading）
JSONB 字段    JSON 字符串序列化后作为一个 CSV 列值
标题行        第一行为字段名，顺序与本文档各表字段定义一致
```

### 5.3 NDJSON 规范

```
编码          UTF-8，无 BOM
行格式        每行一个合法 JSON 对象，行尾换行符 \n
时间戳        ISO 8601 字符串，含时区 +08:00
JSONB 字段    作为原生 JSON 嵌套对象/数组，不序列化为字符串
NULL          JSON null
ENUM/VARCHAR  JSON string
BIGINT        JSON number
```

### 5.4 压缩

所有归档文件在写入存储前使用 **gzip** 压缩（扩展名 `.csv.gz` / `.ndjson.gz`），预期压缩比 5:1 ~ 10:1。

---

## 6. 文件命名与目录结构

### 6.1 目录结构

```
archive/
├── snapshots/                              # 关联快照（每次归档时更新）
│   ├── fleet_snapshot_20250301.csv.gz
│   ├── vehicle_snapshot_20250301.csv.gz
│   ├── device_snapshot_20250301.csv.gz
│   ├── driver_snapshot_20250301.csv.gz
│   └── geo_zone_snapshot_20250301.csv.gz
│
├── location_point/
│   ├── 2025/
│   │   ├── location_point_2025_01.csv.gz
│   │   ├── location_point_2025_02.csv.gz
│   │   └── ...
│   └── 2026/
│       └── ...
│
├── track_segment/
│   └── 2025/
│       ├── track_segment_2025_Q1.csv.gz    # 季度粒度（行数少，无需月粒度）
│       └── ...
│
├── work_session/
│   └── 2025/
│       └── work_session_2025_Q1.csv.gz
│
├── event/
│   └── 2025/
│       ├── event_2025_01.ndjson.gz
│       └── ...
│
├── command_log/
│   └── 2025/
│       └── command_log_2025_Q1.csv.gz
│
└── device_vehicle_bind/
    └── device_vehicle_bind_2024.csv.gz     # 年度粒度
```

### 6.2 文件命名规则

```
{table_name}_{period}.{format}.gz

period 格式：
  月粒度   YYYY_MM     如 2025_01
  季度     YYYY_QN     如 2025_Q1
  年度     YYYY        如 2024

示例：
  location_point_2025_01.csv.gz
  event_2025_01.ndjson.gz
  track_segment_2025_Q1.csv.gz
  device_vehicle_bind_2024.csv.gz
  vehicle_snapshot_20250301.csv.gz    # 快照带完整日期 YYYYMMDD
```

### 6.3 校验文件

每个归档文件同目录下放置同名 `.sha256` 文件，记录行数与摘要：

```
# location_point_2025_01.csv.gz.sha256
sha256: a3f2e1d4c8b7...
rows: 12580430
exported_at: 2025-03-01T02:15:33+08:00
source_table: location_point
period: 2025_01
```

---

## 7. 完整性校验清单

在执行**主库删除 / 分区 DROP** 前，须逐项确认以下条件：

```
归档完整性校验（以 location_point_2025_01 为例）
──────────────────────────────────────────────
[ ] 归档文件存在：archive/location_point/2025/location_point_2025_01.csv.gz
[ ] 校验文件存在：archive/location_point/2025/location_point_2025_01.csv.gz.sha256
[ ] 行数一致：归档文件行数 == 主库分区行数
      SELECT COUNT(*) FROM location_point_2025_01;
[ ] SHA-256 校验通过（解压后重新计算与 .sha256 文件一致）
[ ] 快照文件已在本次归档中更新（fleet / vehicle / device / driver / geo_zone）
[ ] 业务确认：近 30 天内无人查询该时段历史轨迹
[ ] 通知相关管理员：归档操作前知会干系人
[ ] 主库备份：执行 pg_dump 完整备份后再删除
[ ] 操作留痕：在运维日志中记录操作人、操作时间、删除范围
```

**数据保留年限参考**

| 表 | 主库保留 | 归档保留下限 | 说明 |
|----|---------|------------|------|
| `location_point` | 近 3 个月 | 10 年 | 超期经管理员审批后删除 |
| `track_segment` | 近 3 个月 | 10 年 | 同上 |
| `work_session` | 近 3 个月 | 10 年 | 同上 |
| `event` | 近 3 个月 | **3 年**（合规要求） | `severity=3` 超速/越界/禁运记录，按行业监管要求执行 |
| `command_log` | 近 3 个月 | 3 年 | 3 年后可清理 |
| `device_vehicle_bind` | 永久（数量极少） | 10 年 | 视业务决定 |
| 快照表 | 主库全量 | 每归档一份，保留最新 2 份 | 替换旧快照时旧版再保留一个版本 |

---

*本文档由 TMSS 开发团队维护，变更须更新版本号并同步 `docs/DEVPLAN.md` 的相关任务项。*
