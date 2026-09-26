"""TEI 就绪巡检：确认 embedding 与 rerank 两个端点**能被项目代码路径调通**。

为什么需要它
------------
TEI 由使用者在 Docker 里另行启动（**不在 `compose.yaml` 内**，那里只有 `agent_service`）。
它有两个特点，使得「凭经验探活」一定会出错：

1. **两个端点的请求体 schema 不同**：`/embeddings` 是 OpenAI 兼容（`input`），
   `/rerank` 是 TEI 原生（`query`/`texts`/`top_n`）。同一个 11435 端口上还多挂了一条
   TEI 原生的 `/embed`。手写 curl 用错 schema 会得到 **422**，而 422 常被误读成
   「服务没起来」——2026-09-27 就踩过一次。
2. **它宕机后不报错**，只表现为「检索降级 / rerank 分数全 None」——
   这样测出来的数据**看起来像结论**，实际是环境噪声。

本脚本**复用项目自己的调用路径**（`rag.embeddings` / `rag.reranker`）发最小请求，
因此「代码怎么发」与「环境通不通」用的是**同一个真源**，不存在第二份写法。

用法::

    PYTHONPATH=src python scripts/tei_ready.py

退出码：0 = 两端都通；1 = 至少一个不通（并打印该怎么办）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许以脚本方式直接运行（无需 `python -m`）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PROBE_TEXT = "探活"


def probe_embedding() -> tuple[bool, str]:
    """用**项目代码路径**探 embedding。"""
    from core.settings import settings
    from rag.embeddings import get_embeddings

    try:
        vec = get_embeddings().embed_query(PROBE_TEXT)
    except Exception as exc:  # noqa: BLE001 — 巡检要把任何失败如实报出
        return False, f"{type(exc).__name__}: {exc}"[:120]
    dim = len(vec)
    expect = settings.EMBEDDING_DIM
    if dim != expect:
        return False, f"维度不符：得到 {dim}，期望 {expect}（检查 .env 的 EMBEDDING_DIM）"
    return True, f"dim={dim}"


def probe_rerank() -> tuple[bool, str]:
    """用**项目代码路径**探 rerank。"""
    from langchain_core.documents import Document

    from core.settings import settings
    from rag.reranker import rerank

    # rerank() 内部按部署开关短路，探活时必须显式打开
    settings.RERANK_ENABLED = True
    try:
        out = rerank(
            PROBE_TEXT,
            [Document(page_content=f"{PROBE_TEXT}文本", metadata={"content_hash": "probe"})],
            top_k=1,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:120]
    score = out[0].metadata.get("rerank_score") if out else None
    if score is None:
        return False, "rerank 未打分（返回 None）—— reranker 疑似未真正执行"
    return True, f"score={float(score):.4f}"


def main() -> int:
    from core.settings import settings

    print("=" * 68)
    print("  TEI 就绪巡检（复用项目代码路径）")
    print("=" * 68)
    print(f"  embedding : {settings.EMBEDDING_API_BASE}/embeddings  （OpenAI 兼容 schema）")
    print(f"  rerank    : {settings.RERANK_LOCAL_URL}/rerank      （TEI 原生 schema）")
    print()

    results = {
        "embedding": probe_embedding(),
        "rerank": probe_rerank(),
    }
    for name, (ok, detail) in results.items():
        mark = "✓ 就绪" if ok else "✗ 不可用"
        print(f"  {name:<12}{mark:<10}{detail}")

    if all(ok for ok, _ in results.values()):
        print("\n⇒ 两端就绪，可以跑检索 / 门禁 / 盘点脚本。")
        return 0

    print("\n⇒ 未就绪。你只需要做一件事：**启动 Docker 里的 embedding 与 rerank 容器**。")
    print("  端口取自 .env（EMBEDDING_API_BASE / RERANK_LOCAL_URL），别写死。")
    print("  首次部署用：scripts/tei_deploy.ps1（含部署后验证）；日常用 docker start。")
    print("  bge-m3 加载约需 30~60s，启动后请等待再重跑本脚本。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
