"""评估适配器：对接 edu-agent 的 retriever 与 get_llm。"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.embeddings import Embeddings

from core.llm import get_llm
from evaluation.dataset import EvalSample
from rag.retriever import aretrieve_evidence_with_retry

logger = logging.getLogger(__name__)


async def retrieve_contexts(
    query: str, *, k: int, use_rerank: bool
) -> tuple[list[str], list[dict[str, object]]]:
    """跑生产检索链，抽出**逐条证据正文**作为 RAGAS 的 contexts。

    ⚠️ 这里**不返回 `fused.final_context`**，这是刻意的口径选择：

    `final_context` 在 `rag/fusion.py` 里是
    ``"\\n\\n".join(parts)``，而 `parts` 就是各条 evidence 的格式化文本。
    若把它与各条 evidence
    **一起**作为 contexts 交给 RAGAS，指标会因「拼接体 vs 成员」的
    自我包含关系被系统性抬高 —— 而且 ``not in contexts`` 只能挡住
    完全相同的整串，挡不住这种包含关系。

    另外 `context_precision` 需要**多条独立上下文**才有判别力；把拼接体
    作为单条 context 会让它退化成「这一大坨里有没有相关内容」。

    评测口径因此定义为「chunk 粒度」：一条 evidence = 一条 context。
    ★ 下面那个回退到 `final_context` 的分支自 KG 移除后已不可达（`final_context`
    就是文本证据的拼接，证据为空则它必为空）；保留它只为防止 fusion 将来改口径时
    静默返回空列表。
    """
    fused, _ver = await aretrieve_evidence_with_retry(
        query=query,
        k=k,
        use_rerank=use_rerank,
        max_retries=0,
        use_llm_verify=False,
    )
    contexts: list[str] = []
    details: list[dict[str, object]] = []
    seen: set[str] = set()
    for ev in fused.text_evidences:
        text = (ev.content or "").strip()
        if text and text not in seen:
            seen.add(text)
            contexts.append(text)
            details.append(
                {
                    "context_index": len(contexts) - 1,
                    "source": ev.source,
                    "section_path": ev.section_path,
                    "chunk_id": ev.chunk_id,
                    "parent_id": ev.parent_id,
                    "collection": ev.collection,
                    "score": ev.score,
                    "recall_score": ev.recall_score,
                    "rerank_score": ev.rerank_score,
                    "metadata": {
                        key: ev.metadata.get(key)
                        for key in (
                            "category",
                            "content_type",
                            "_retrieval_layer",
                            "_route_type",
                            "recall_routes",
                            "_hyde_fallback",
                            "_window_expanded",
                        )
                        if ev.metadata.get(key) is not None
                    },
                }
            )
    if not contexts and fused.final_context.strip():
        # 兜底（当前不可达，理由见 docstring）：证据为空但融合体非空时至少给一条
        contexts = [fused.final_context.strip()]
        details = [{"context_index": 0, "source": "", "section_path": ""}]
    return contexts or [""], details


async def generate_answer(query: str, contexts: list[str], *, timeout: float) -> str:
    """基于检索上下文生成答案（评测用，非产品对话路径）。"""
    ctx = "\n\n".join(c for c in contexts if c)[:6000]
    prompt = (
        "你是 408 考研辅导助手。仅依据下列资料回答问题；"
        "资料不足时明确说明无法回答。\n\n"
        f"【资料】\n{ctx}\n\n【问题】\n{query}"
    )
    llm = get_llm(streaming=False, temperature=0.3)
    try:
        raw = await asyncio.wait_for(llm.ainvoke(prompt), timeout=timeout)
    except Exception:
        logger.warning("评测答案生成失败 query=%s", query[:40], exc_info=True)
        return ""
    content = getattr(raw, "content", raw)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return str(content or "").strip()


async def fill_sample(
    sample: EvalSample, *, k: int, use_rerank: bool, answer_timeout: float
) -> EvalSample:
    sample.contexts, sample.retrieval_details = await retrieve_contexts(
        sample.query, k=k, use_rerank=use_rerank
    )
    sample.answer = await generate_answer(sample.query, sample.contexts, timeout=answer_timeout)
    return sample


def build_judge_llm(timeout: int | None = None):
    """RAGAS judge：复用项目 LLM（ChatOpenAI → LangchainLLMWrapper）。

    ``settings.LLM_TIMEOUT`` 在客户端创建时会同时写入 sync/async httpx client。
    RAGAS 的 ``RunConfig`` 后续只更新 wrapper 的 ``request_timeout``，不会可靠地更新
    已创建的底层 client；因此这里显式同步三处超时，避免仍被旧的 90 秒 client 截断。
    """
    from ragas.llms import LangchainLLMWrapper  # type: ignore[import-not-found]

    llm = get_llm(streaming=False, temperature=0.0)
    # DashScope 等网关上强制 JSON，降低 judge 解析失败率
    existing = dict(getattr(llm, "model_kwargs", None) or {})
    existing["response_format"] = {"type": "json_object"}
    try:
        # 用 setattr 而不是 `llm.model_kwargs = ...`：get_llm 现在可能返回 FakeToolModel
        # （USE_FAKE_MODEL=true 时，见 core.llm），它没有 model_kwargs 属性 ——
        # 直接赋值在类型上不成立（pyrefly 会报 missing-attribute）。
        # 运行时两者等价，setattr 对任意对象都成立。
        setattr(llm, "model_kwargs", existing)
    except Exception:
        logger.debug("无法设置 response_format，跳过", exc_info=True)
    judge = LangchainLLMWrapper(langchain_llm=llm)
    if timeout is not None:
        target = getattr(judge, "langchain_llm", llm)
        setattr(target, "request_timeout", float(timeout))
        for client_name in ("root_client", "root_async_client"):
            client = getattr(target, client_name, None)
            if client is not None:
                setattr(client, "timeout", float(timeout))
    return judge


def build_embeddings_for_relevancy() -> Embeddings | None:
    """`answer_relevancy` 要用的 embeddings —— 复用检索链的同一套（TEI / 哈希桩）。

    ★ 返回 None 的语义是「**该指标不要测**」，调用方必须把它从 `metrics` 里摘掉。
    原因：ragas 0.4.3 的 `aevaluate` 对 `embeddings is None` 的指标会**自动兜底**注入
    一套默认 OpenAI embedding —— 于是「不注入」会静默变成「换一套向量度量」，
    该指标与其余三个不同源、口径不可比。摘掉它，报告里的指标集才保持同口径。

    ★ 不包 `LangchainEmbeddingsWrapper`：`ResponseRelevancy` 是 dataclass，
    `calculate_similarity` 只调用 `embed_query` / `embed_documents`，
    langchain `Embeddings` 原生满足，包装只会引入 deprecated 警告与易错的 kwarg 名。
    """
    try:
        from rag.embeddings import get_embeddings

        return get_embeddings()
    except Exception:
        logger.warning("初始化 embeddings 失败，answer_relevancy 将不参与本次评测", exc_info=True)
        return None
