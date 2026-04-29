# TMSS — Truck Monitoring System Simplify

基于 GPS + 4G + ESP32 的车队实时监控平台，支持超速/越界告警、作业状态识别、实时大屏展示。

## 快速启动

```bash
# 1. 复制并填写环境变量
cp .env.example .env

# 2. 启动 Redis（PostgreSQL 使用已有实例时跳过 --profile local-db）
docker compose up -d
# 或同时启动本地 PostgreSQL
docker compose --profile local-db up -d

# 3. 初始化数据库
alembic upgrade head

# 4. 启动服务（HTTP :8900 + TCP :8901）
python -m app.main
```

## 目录结构

```
app/
├── config.py            # 环境变量与配置
├── core/                # 枚举、异常、任务注册表、设备注册表、EventBus
├── db/                  # asyncpg 连接池、SQL 常量、Repository
├── cache/               # Redis 连接池、Session/心跳/天气缓存
├── http/                # FastAPI 工厂、路由、依赖注入
├── tcp/                 # asyncio TCP 服务、帧解析、Handler
├── services/            # 业务逻辑（认证、告警、围栏、天气等）
├── models/              # Pydantic 模型（HTTP 请求/响应、TCP 报文）
└── tasks/               # 后台定时任务
alembic/                 # 数据库迁移脚本
docs/                    # 详细文档
```

## 文档

| 文档 | 说明 |
| --- | --- |
| [详细说明](docs/详细说明.md) | 功能需求、通讯协议、TCP 指令表 |
| [DEVPLAN](docs/DEVPLAN.md) | 开发阶段与任务进度（当前：阶段 5/10 完成） |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 架构规范与强制约定 |
| [DATABASE](docs/DATABASE.md) | 数据库表结构与索引策略 |
| [TECHSTACK](docs/TECHSTACK.md) | 技术选型与依赖清单 |

## 当前进度

```
✅ 阶段 1–5  地基 / 数据访问层 / 认证 / HTTP API / TCP 服务基础
⬜ 阶段 6    业务逻辑核心（超速/围栏/状态机）
⬜ 阶段 7–10 SSE 推送 / 后台任务 / 前端 / 大屏
```
