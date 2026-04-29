from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 服务端口
    tcp_port: int = 9000
    http_port: int = 8080

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
