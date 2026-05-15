# TMSS — Truck Monitoring System Simplify

基于 GPS + 4G + ESP32 的车队实时监控平台，支持超速/越界告警、作业状态识别、实时大屏展示。

## 快速启动

```bash
# 1. 复制并填写环境变量
cp .env.example .env

# 2. 激活 Python 虚拟环境（若无 `.venv`，先 `python3 -m venv .venv`，再在虚拟环境中根据 `pyproject.toml` 安装依赖）
source .venv/bin/activate

# 3. 启动依赖服务（本机用虚拟环境跑后端时，请勿默认启动 compose 里的 app，否则会占用 8900/8901）
docker compose up -d redis
# 使用 Compose 内 PostgreSQL（映射到宿主机 5433，见 docker-compose.yml；.env 中 DATABASE_URL 需用 5433）
docker compose --profile local-db up -d redis postgres
# 若整套后端也在容器里跑（则不要再执行下面的 python -m app.main / start.sh）
# docker compose up -d

# 4. 初始化数据库
alembic upgrade head

# 5. 启动服务（HTTP :8900 + TCP :8901）
python -m app.main
```

**后台运行（推荐使用 start.sh）：**

```bash
bash start.sh restart  # 先停再起（见脚本用法）
bash start.sh           # 后台启动（日志写入 backend.log，自动加分隔线）
bash start.sh status    # 查看运行状态与监听端口
bash start.sh log       # 实时查看日志（tail -f）
bash start.sh stop      # 停止服务
```

## 目录结构

```
app/
├── config.py            # 环境变量与配置
├── core/                # 枚举、异常、任务注册表、设备注册表、EventBus
├── db/                  # asyncpg 连接池、SQL 常量、Repository
├── cache/               # Redis 连接池、Session/心跳/天气/断线缓存
├── http/                # FastAPI 工厂、路由、依赖注入
├── tcp/                 # asyncio TCP 服务、帧解析、Handler
├── services/            # 业务逻辑（认证、告警、围栏、天气、轨迹段扫描等）
├── models/              # Pydantic 模型（HTTP 请求/响应、TCP 报文）
└── tasks/               # 后台定时任务
alembic/                 # 数据库迁移脚本
docs/                    # 详细文档
frontend/                # Vue 3 + Vite 前端
nginx.conf               # 生产环境 nginx（仓库根目录；compose --profile production 挂载）
```

## 文档

| 文档 | 说明 |
| --- | --- |
| [详细说明](docs/详细说明.md) | 功能需求、通讯协议、TCP 指令表 |
| [DEVPLAN](docs/DEVPLAN.md) | 开发阶段与任务进度 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 架构规范与强制约定 |
| [DATABASE](docs/DATABASE.md) | 数据库表结构与索引策略 |
| [TECHSTACK](docs/TECHSTACK.md) | 技术选型与依赖清单 |
| [FRONTEND](docs/FRONTEND.md) | 前端设计、目录结构、路由与部署说明 |
| [FEATURE_FLEET_CAPTAIN_V2](docs/FEATURE_FLEET_CAPTAIN_V2.md) | 车队长权限 V2 功能规格（待确认） |

## 当前进度

```
✅ 阶段 1   地基（工程骨架 + 数据库迁移 + Core 模块）
✅ 阶段 2   数据访问层（DB/Redis 连接池 + Repository）
✅ 阶段 3   认证与权限（Session + 登录/登出 + 依赖注入）
✅ 阶段 4   HTTP 管理 API（CRUD 接口 + 数据隔离）
✅ 阶段 5   TCP 服务基础（设备接入 + 心跳 + 时间/天气）
✅ 阶段 6   业务逻辑核心（超速/围栏/状态机/指令下发）
✅ 阶段 7   实时推送（EventBus + SSE 路由）
✅ 阶段 8   后台任务（心跳扫描 + 分区自动创建）
✅ 阶段 9   前端基础（Vue 骨架 + 登录 + 管理页）
✅ 阶段 10  大屏（高德地图 + SSE + 实时大屏）
✅ 阶段 11  历史轨迹查询（轨迹回放 + GCJ-02 转换 + 管理员删除）
✅ 阶段 12  系统完善（家用车型 / ICCID 补全 / UI 科技化）
✅ 阶段 13  作业识别增强（装/卸标注 / 历史重分割 / 大屏等）
✅ 阶段 14  轨迹分段重构（六类型分段等）
✅ 阶段 15  大屏与设备一致性（日期筛选 / 轨迹高亮 / IMEI 恢复语义）
⬜ 待开发   ECharts 统计图（大屏饼图/折线图）
⬜ 待开发   车队长权限 V2（FEATURE_FLEET_CAPTAIN_V2.md）
```

## 端口速查

| 服务 | 端口 |
| --- | --- |
| HTTP API（FastAPI） | **8900** |
| TCP 设备接入 | **8901** |
| Vite 开发服务器（前端） | **5173** |
| Redis（docker compose） | **6379** |
| PostgreSQL（compose `local-db` 映射到宿主机） | **5433** → 容器内 5432 |
| nginx 静态站（compose `production` profile） | **80** |
