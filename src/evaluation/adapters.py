"""评估适配器：对接 edu-agent 的 retriever 与 get_llm。"""

from __future__ import annotations

import asyncio
import logging

from core.llm import get_llm
from evaluation.dataset import EvalSample
from rag.retriever import aretrieve_evidence_with_retry

logger = logging.getLogger(__name__)


async def retrieve_contexts(query: str, *, k: int, use_rerank: bool) -> list[str]:
    """跑生产检索链，抽出 final_context / evidence 文本列表。"""
    fused, _ver = await aretrieve_evidence_with_retry(
        query=query,
        k=k,
        use_rerank=use_rerank,
        max_retries=0,
        use_llm_verify=False,
    )
    contexts: list[str] = []
    if fused.final_context and fused.final_context.strip():
        contexts.append(fused.final_context)
    for ev in fused.text_evidences:
        text = (ev.content or "").strip()
        if text and text not in contexts:
            contexts.append(text)
    return contexts or [""]


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
    sample.contexts = await retrieve_contexts(sample.query, k=k, use_rerank=use_rerank)
    sample.answer = await generate_answer(sample.query, sample.contexts, timeout=answer_timeout)
    return sample


def build_judge_llm():
    """RAGAS judge：复用项目 LLM（ChatOpenAI → LangchainLLMWrapper）。"""
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
    return LangchainLLMWrapper(langchain_llm=llm)


def build_embeddings_for_relevancy():
    """answer_relevancy 需要 embeddings；复用 TEI。失败返回 None（跳过该指标）。"""
    try:
        from rag.embeddings import get_embeddings

        return get_embeddings()
    except Exception:
        logger.warning("初始化 embeddings 失败，answer_relevancy 可能不可用", exc_info=True)
        return None
