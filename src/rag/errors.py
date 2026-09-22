"""检索域异常层级：让「失败的类型」可被**程序**判断，而不是只留一句字符串。

## 为什么需要它

检索链的失败有三种本质不同的原因，处置方式完全不同：

| 类别 | 典型来源 | 该怎么做 |
|---|---|---|
| `RetrievalUnavailable` | TEI / Chroma 超时、连接被拒、HTTP 5xx | 可重试、可降级；日志 **WARNING** |
| `RagInternalError` | 数据契约被破坏、返回 NaN、解析失败 | 代码缺陷；日志 **ERROR** + 告警 |

在这之前，这些失败一律被抛成通用 `RuntimeError`，到边界处被抹平成同一句
「检索失败：…」。后果是**日志里出现 ERROR 时无法判断严重程度** ——
一次 TEI 抖动和一次真代码缺陷长得一模一样，值班的人只能靠猜。

## 为什么不设 `RetrievalEmpty`

设计稿里列了这一类，但**本项目不实现它**：空结果走的是**正常返回路径**
（`schema.evidence.RetrievalResult.status == "empty"`），不是异常。
把「正常」做成异常会让两者共用同一条控制流 —— 那正是本模块要消除的问题。
「知识库确实没有」应当由 `status` 表达，而不是由 `except` 表达。
"""

from __future__ import annotations

import asyncio

import httpx

__all__ = [
    "RagError",
    "RetrievalUnavailable",
    "RagInternalError",
    "classify_retrieval_error",
]


class RagError(Exception):
    """检索域异常基类。

    捕获这一层即可拿到「检索相关的一切失败」，而不必 catch-all。
    """


class RetrievalUnavailable(RagError):
    """外部依赖不可用或超时（TEI embedding / rerank、Chroma、网络）。

    语义是**暂时性**的：同一请求稍后重试可能成功。
    因此调用方应当降级或重试，日志用 WARNING —— **不应触发告警**。
    """


class RagInternalError(RagError):
    """检索链内部缺陷：数据契约被破坏、上游返回非法值、解析失败。

    语义是**非暂时性**的：重试无用，必须有人去看。
    日志必须用 ERROR/exception 并保留堆栈。
    """


# 判定为「外部依赖不可用」的异常类型。
# httpx.HTTPError 已覆盖 TimeoutException / TransportError / HTTPStatusError（4xx/5xx）；
# asyncio.TimeoutError 在 3.11+ 即内置 TimeoutError，两者都列上以兼容旧写法。
_UNAVAILABLE_TYPES: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
)


def classify_retrieval_error(exc: BaseException) -> RagError:
    """把任意异常归类到检索域层级。

    这是**兜底**判据，不是主要机制 —— 精确归类要求**调用点自己抛出正确的类型**
    （见 `rag.embeddings` 的 TEI 调用）。本函数负责那些没被标注过的异常，
    避免它们被静默当成"代码缺陷"或反之。

    规则：
    1. 已经是 `RagError` → 原样返回（保留调用点给出的更精确语义）。
    2. 网络/超时类 → `RetrievalUnavailable`。
    3. 其余 → `RagInternalError`（**宁可误报为缺陷，也不要漏报**：
       漏报会让真缺陷永远只表现为"答得不对"）。

    `__cause__` 保留原异常，便于 `logger.exception` 打印完整堆栈。
    """
    if isinstance(exc, RagError):
        return exc

    if isinstance(exc, _UNAVAILABLE_TYPES):
        return RetrievalUnavailable(str(exc))

    return RagInternalError(str(exc))
