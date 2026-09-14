"""服务启动入口：python src/run_service.py"""

import asyncio
import logging
import sys

import uvicorn

from core import settings
from core.settings import PROJECT_ROOT


def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL.to_logging_level())
    # Windows 下默认 ProactorEventLoop 与异步 DB 驱动不兼容，切换到 SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(
        "service.service:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_dev(),
        # dev 热重载只监听源码目录：运行时写 chroma_db / *.db 等数据文件不应触发重启
        reload_dirs=[str(PROJECT_ROOT / "src")],
        timeout_graceful_shutdown=settings.GRACEFUL_SHUTDOWN_TIMEOUT,
    )


if __name__ == "__main__":
    main()
