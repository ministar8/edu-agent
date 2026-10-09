"""热路径记忆写入：await + 超时 + 失败不拖垮主流程。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from core.settings import settings

logger = logging.getLogger(__name__)


_READ_STATUS_SUCCESS = "success"
_READ_STATUS_FAILED = "failed"


async def safe_remember[T](
    factory: Callable[[], Awaitable[T]],
    *,
    label: str = "memory",
) -> T | None:
    """执行记忆写入；超时或异常时返回 None，不向调用方抛错。

    刻意 **await** 而非 create_task：假异步会丢异常、难观测，还可能在
    进程退出时被取消。

    ★ 写侧继续用本函数（状态无消费者）；**读侧**要用 `safe_remember_status` ——
      这里返回的 `None` 把「超时/异常」和「读到空值」压成同一个值，
      正是 B4 要消除的折叠（`teaching_graph.py` 曾在此 `or ""`，于是一次 Store 超时
      与「画像确实是空的」在下游不可区分，而后者是真缺陷、前者是 `missing_premise`）。
    """
    value, _status = await safe_remember_status(factory, label=label)
    return value


async def safe_remember_status[T](
    factory: Callable[[], Awaitable[T]],
    *,
    label: str = "memory",
) -> tuple[T | None, str]:
    """同 `safe_remember`，但把结果与**读链状态**分开返回。

    状态值域（与 `EVIDENCE_CHAIN.md` §5 B4 的 `memory_read_status` 对齐）：
    - `success`：调用完成（**不代表有卡** —— 空串由调用方判成 `empty`）；
    - `failed`：超时或抛错 ⇒ 下游必须记 `None`（未测量），**绝不**记 False。

    ★ 本函数不返回 `not_attempted` / `empty`：那两个是**调用方**才知道的事实
      （有没有 `user_id`、拿到的卡是不是空串），在这里造出来等于替调用方猜。
    """
    timeout = settings.MEMORY_WRITE_TIMEOUT
    try:
        value = await asyncio.wait_for(factory(), timeout=timeout)
    except TimeoutError:
        logger.warning("长期记忆写入超时（%s，>%.1fs），已忽略", label, timeout)
        return None, _READ_STATUS_FAILED
    except Exception:
        logger.warning("长期记忆写入失败（%s），已忽略", label, exc_info=True)
        return None, _READ_STATUS_FAILED
    return value, _READ_STATUS_SUCCESS
