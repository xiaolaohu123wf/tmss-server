import asyncio
import logging

import structlog
import uvicorn

from app.config import settings
from app.http.app import create_app

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()


async def main() -> None:
    await logger.ainfo("tmss_starting", tcp_port=settings.tcp_port, http_port=settings.http_port)

    # 启动 TCP 服务器
    from app.tcp.server import start_tcp_server
    tcp_server = await start_tcp_server()

    http_app = create_app()
    config = uvicorn.Config(
        http_app,
        host="0.0.0.0",
        port=settings.http_port,
        loop="none",
        log_config=None,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        tcp_server.close()
        await tcp_server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
