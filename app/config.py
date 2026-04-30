from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 服务端口（.env 优先；下方为无 .env 时的兜底默认值）
    tcp_port: int = 8901
    http_port: int = 8900

    # TCP 调试：为 True 时每条收发额外 print 到 stdout（高流量慎用）；环境变量 TCP_RAW_PRINT
    tcp_raw_print: bool = False

    # 为 True 时 /api/admin/tcp-messages 对任意来源免登录（仅本机调试或 Docker 端口映射时用，勿上生产）
    tcp_messages_public: bool = False

    # 数据库
    database_url: str = Field(min_length=1)
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20

    # Redis
    redis_url: str = Field(min_length=1)

    # 业务兜底（运行时以 business_config 表为准）
    park_threshold_min: int = 10
    alert_cooldown_s: int = 10
    hb_timeout_s: int = 90

    # 外部服务
    weather_api_url: str = "https://wttr.in"

    # 安全
    session_secret: SecretStr = Field(min_length=16)
    bcrypt_cost: int = 12


settings = Settings()  # type: ignore[call-arg]
