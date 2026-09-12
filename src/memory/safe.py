"""热路径记忆写入：await + 超时 + 失败不拖垮主流程。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from core.settings import settings

logger = logging.getLogger(__name__)


async def safe_remember[T](
    factory: Callable[[], Awaitable[T]],
    *,
    label: str = "memory",
) -> T | None:
    """执行记忆写入；超时或异常时返回 None，不向调用方抛错。

    刻意 **await** 而非 create_task：假异步会丢异常、难观测，还可能在
    进程退出时被取消。
    """
    timeout = settings.MEMORY_WRITE_TIMEOUT
    try:
        return await asyncio.wait_for(factory(), timeout=timeout)
    except TimeoutError:
        logger.warning("长期记忆写入超时（%s，>%.1fs），已忽略", label, timeout)
        return None
    except Exception:
        logger.warning("长期记忆写入失败（%s），已忽略", label, exc_info=True)
        return None
