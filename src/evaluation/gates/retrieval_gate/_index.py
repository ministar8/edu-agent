"""门禁临时索引：构建 + 就绪屏障。"""

from __future__ import annotations

import logging

from ._modes import _MODE_SETTINGS, GATE_RERANK_MODE, GATE_USE_REAL_EMBEDDING, GATE_USE_REAL_RERANK

logger = logging.getLogger(__name__)


def configure_for_gate(persist_dir: str) -> None:
    """把 settings 切成"离线可跑"形态，并重置模块级单例。

    必须在跑检索前调用。之所以是函数而不是模块级副作用：``settings`` 是 import 期
    构造的单例，测试和 CLI 需要各自决定何时生效。

    ``CHROMA_PORT = 1`` 是为了让 ``VectorStoreManager`` 走 PersistentClient 分支
    （端口 1 不可能有真实服务），从而把索引落到临时目录而不是真实的 ``chroma_db/``。

    **LLM 也必须显式拉回假网关**（不只是设 ``USE_FAKE_MODEL``）：检索链的
    decompose / HyDE 会调 LLM，若这里漏掉，本地（.env 配了真实 key）会真的打线上模型
    —— 温度 0.3，基线不可复现且产生费用；CI（无 key）则抛
    ``openai.OpenAIError: Missing credentials``，实测让 40 条 query 里 6 条崩溃。
    settings 侧已有"USE_FAKE_MODEL 拉回假网关"的逻辑，这里再显式设一次是**故意的重复**：
    门禁的正确性不该依赖 settings 的默认推导，显式声明才能保证任何环境下行为一致。

    同理，``rerank`` 三态由 ``GATE_RERANK_MODE`` 决定，覆盖见 ``_MODE_SETTINGS``：

    - ``on``：默认打开 ``RERANK_ENABLED`` 与 ``USE_FAKE_RERANK``，用于无 TEI 的可复现门禁
      （★ 不是逐位确定：抖动来自**并列打破** —— 下游按分数单键排序处（如 ``dedup_same_section``）
      的并列次序受**并发路由完成次序**影响；**不是 HNSW**，图本身实测确定，归因见
      ``docs/ARCHITECTURE_RETRIEVAL.md`` §6.3(b)。fake 路由指标有 ±2e-4 量级抖动，
      容差 0.02 盖得住）；
      真实 embedding 发布前若设置 ``GATE_USE_REAL_RERANK=1``，则改用 `.env` 中的 TEI reranker，
      并写入独立的真实 embedding + 真实 rerank 基线。
    - ``disabled``：``RERANK_ENABLED=False``，但检索链**仍然** ``use_rerank=True``
      —— 这正是要复现的生产关闭态（要求了但部署关掉）。该态必须断言"一条都没重排"，
      否则说明部署开关失效（见 ``_assert_route_preconditions``）。

    真实 embedding 路由（``GATE_USE_REAL_EMBEDDING``）是唯一**需要** TEI 的一条：
    它关掉 ``USE_FAKE_EMBEDDING``，改用 ``.env`` 里的 ``EMBEDDING_API_BASE``
    （这里不写死地址 —— 生产地址由 ``.env`` 提供）。**LLM 仍然拉回假网关**：
    那件事与 embedding 无关，且 CI/本地都不该为了跑门禁去打真实模型。
    """
    from core.settings import GATEWAY_DEFAULT_MODEL, Gateway, make_model_ref, settings
    from rag.common import vectorstore as vs
    from rag.retrieval import semantic_cache as sc

    settings.USE_FAKE_EMBEDDING = not GATE_USE_REAL_EMBEDDING
    settings.CHROMA_PORT = 1
    settings.CHROMA_PERSIST_DIR = persist_dir
    settings.SEMANTIC_CACHE_ENABLED = False
    if GATE_USE_REAL_RERANK:
        settings.RERANK_ENABLED = True
        settings.USE_FAKE_RERANK = False
    else:
        settings.RERANK_ENABLED, settings.USE_FAKE_RERANK = _MODE_SETTINGS[GATE_RERANK_MODE]

    settings.USE_FAKE_MODEL = True
    fake_ref = make_model_ref(Gateway.FAKE, GATEWAY_DEFAULT_MODEL[Gateway.FAKE])
    settings.DEFAULT_MODEL = fake_ref
    settings.LLM_MODEL = fake_ref

    # 模块级单例在 import 期已按旧 settings 构造，必须重置
    vs._vector_store_manager = None
    sc._semantic_cache = None


def wait_for_index_ready(
    categories: list[str],
    *,
    retries: int = 8,
    delay: float = 0.5,
    repair: bool = True,
) -> dict[str, int]:
    """等每个集合的 HNSW 索引可查询，返回 {集合: 成功前的失败次数}。

    就绪检测实现在 ``VectorStoreManager.wait_until_ready``（生产路径同款）。

    ``repair=True`` 时，对"段文件未落盘"的集合做**一次重建后重试**。门禁这么做有理由：
    这是**一次性索引**，重建无副作用且只要几秒；而该故障在进程内无法等待恢复
    （实测「丢弃句柄」「重开 client」均无效，只有 ``delete_collection`` + 重新入库有效）。
    门禁的价值是稳定反映检索质量，不该被上游索引故障污染成"随机失败"。

    生产路径**不做**自动重建 —— 那里删除集合意味着真实数据丢失，必须人工确认。
    """
    from rag.common import vectorstore as vs

    manager = vs.get_vector_store_manager()
    ready: dict[str, int] = {}

    for category in categories:
        try:
            ready[category] = manager.wait_until_ready(category, retries=retries, delay=delay)
            continue
        except RuntimeError as exc:
            if not repair:
                raise
            logger.warning("集合 '%s' 索引不可查询，重建后重试：%s", category, exc)

        manager.delete_collection(category)
        build_index([category])
        ready[category] = manager.wait_until_ready(category, retries=retries, delay=delay)

    return ready


def build_index(categories: list[str] | None = None) -> dict[str, int]:
    """用**生产同源**的 ``rag.ingest_layers.build_all()`` 把知识库索引进当前（临时）向量库。

    覆盖 L1(basic) / L2(advanced) / L3(exams 年 + 章节例题) / code / learning_paths。
    ★ 2026-10-10 起改为调用 ``scripts/ingest_*.py`` **同源**的构建逻辑 ⇒ chunk 数**与生产
    逐位相等**（此前走通用 ``load → clean → split`` 链路、chunk 数与生产不等，见
    ``docs/ARCHITECTURE_RETRIEVAL.md`` §6.3）。
    """
    from rag.common import vectorstore as vs
    from rag.ingest_layers import build_all
    from rag.ingest_layers import code as code_layer

    manager = vs.get_vector_store_manager()
    counts: dict[str, int] = {}

    for category, chunks in build_all().items():
        for chunk in chunks:
            # `category` 是**门禁侧**的类目归属（生产脚本不写该字段，由本门禁补）——
            # category_hit 指标依赖它。
            chunk.metadata["category"] = category
        counts[category] = len(manager.add_documents(chunks, collection_name=category))

    # 无代码文件的科也建空集合（与生产 `ingest_code` 一致，避免召回侧刷 "does not exist"）
    for collection in code_layer.SUBJECT_TO_COLLECTION.values():
        if collection not in counts:
            manager.get_store(collection)
            counts[collection] = 0
    return counts
