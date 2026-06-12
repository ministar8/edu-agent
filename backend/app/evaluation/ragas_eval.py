"""Layer 1: RAGAS 标准指标评估

使用 RAGAS 原生指标 + 系统 LLM 作为 judge。
通过 protocols.py 接口与 RAG 实现解耦。
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from datasets import Dataset
from ragas import RunConfig

from app.config import settings
from app.evaluation.config import EvaluationConfig
from app.evaluation.dataset import EvalSample
from app.evaluation.adapters import get_retriever
from app.rag.rag_utils import estimate_tokens as _estimate_tokens
from app.rag.llm_provider import create_llm, detect_provider

logger = logging.getLogger(__name__)


# ── 模块级常量 ──

_CROSS_SUBJECT_INDICATORS = frozenset({
    "关联", "关系", "区别", "对比", "联系", "分别", "异同",
    "比较", "有什么不同", "有什么关联", "有什么关系",
})

_VALID_COLLECTIONS = frozenset({
    "data_structure", "computer_organization", "operating_system",
    "computer_network", "questions", "learning_paths",
})

_SUBJECT_HINT: dict[str, str] = {
    "data_structure": "数据结构",
    "operating_system": "操作系统",
    "computer_organization": "计算机组成原理",
    "computer_network": "计算机网络",
}

_REFUSAL_PATTERNS = [
    "未包含足够的信息来解答",
    "建议查阅相关教材",
    "根据提供的资料无法回答",
    "根据提供的上下文无法回答",
    "无法回答该问题",
    "无法回答",
    "没有提供",
    "没有相关",
    "没有提到",
    "无法从",
    "无法确定",
    "I don't know",
    "I cannot answer",
]


# ── RAGAS JSON 解析兜底 ──
# Qwen3.6-plus 在 context 不相关时可能输出 {"verdict": "0"} 缺少 reason 字段，
# 导致 pydantic model_validate_json 失败 → RagasOutputParserException → NaN。
# 此 monkey-patch 在 model_validate_json 失败时自动补全缺失字段。

def _is_pydantic_undefined(val: Any) -> bool:
    """Check if value is Pydantic's PydanticUndefined sentinel"""
    try:
        from pydantic_core import PydanticUndefinedType
        return isinstance(val, PydanticUndefinedType)
    except ImportError:
        return "PydanticUndefined" in type(val).__name__


def _safe_model_validate_json(model_class, json_str: str):
    """model_validate_json 的兜底版本：缺失字段自动填充类型默认值"""
    import json as _json
    from pydantic import ValidationError
    try:
        return model_class.model_validate_json(json_str)
    except ValidationError:
        try:
            raw = _json.loads(json_str)
        except _json.JSONDecodeError:
            raise ValidationError(f"Invalid JSON: {json_str[:100]}")
        filled = dict(raw)
        for name, field_info in model_class.model_fields.items():
            if name not in filled:
                if not _is_pydantic_undefined(field_info.default):
                    filled[name] = field_info.default
                elif field_info.default_factory is not None:
                    filled[name] = field_info.default_factory()
                else:
                    ann = field_info.annotation
                    if ann is int:
                        filled[name] = 0
                    elif ann is str:
                        filled[name] = "(auto-filled)"
                    elif ann is float:
                        filled[name] = 0.0
                    elif ann is bool:
                        filled[name] = False
                    else:
                        filled[name] = None
        return model_class.model_validate(filled)


_json_fallback_patched = False


def _patch_ragas_json_fallback():
    """Monkey-patch RAGAS PydanticPrompt.generate_multiple 使用兜底 JSON 解析

    仅在 DashScope（LangchainLLMWrapper）路径下生效，
    因为 InstructorLLM 路径靠 function calling 保证结构化输出。
    幂等：多次调用只 patch 一次。
    """
    global _json_fallback_patched
    if _json_fallback_patched:
        return
    try:
        from ragas.prompt.pydantic_prompt import PydanticPrompt
    except ImportError:
        return

    _orig_generate_multiple = PydanticPrompt.generate_multiple

    async def _patched_generate_multiple(self, *args, **kwargs):
        # 对 LangchainLLMWrapper 路径，替换 model_validate_json
        from ragas.llms.base import LangchainLLMWrapper
        llm = kwargs.get("llm", args[1] if len(args) > 1 else None)
        if isinstance(llm, LangchainLLMWrapper):
            # 临时替换 output_model 的验证方法
            orig_validate = self.output_model.model_validate_json
            self.output_model.model_validate_json = classmethod(
                lambda cls, json_str: _safe_model_validate_json(cls, json_str)
            )
            try:
                return await _orig_generate_multiple(self, *args, **kwargs)
            finally:
                self.output_model.model_validate_json = orig_validate
        else:
            return await _orig_generate_multiple(self, *args, **kwargs)

    PydanticPrompt.generate_multiple = _patched_generate_multiple
    _json_fallback_patched = True
    logger.info("RAGAS PydanticPrompt.generate_multiple patched with JSON fallback")

# ── 答案生成 Prompt ──────────────────────────────────
_ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "你是一名教学答疑助手。请严格遵循以下规则：\n"
        "1. 仅使用下方【上下文】中提供的信息回答问题，禁止使用任何外部知识或自行推断。\n"
        "2. 回答必须紧扣问题，简明扼要，直击要点，不要添加无关背景铺垫。\n"
        "3. 【抗干扰】提供的参考资料中可能包含与当前问题无关或相互冲突的干扰信息。"
        "你必须仅提取与用户问题直接相关的片段进行回答，忽略所有无关的背景铺垫。\n"
        "4. 【部分回答】如果【上下文】中有相关信息，即使信息不完整，也请基于已有信息尽量回答，"
        "并在回答末尾注明\"（以上基于提供的部分资料）\"。\n"
        "5. 不要使用\"可能\"、\"大概\"、\"应该是\"等猜测性表述。\n"
        "6. 【代码与公式规范】如果问题要求代码实现或公式推导，请严格基于上下文提供的算法逻辑或公式进行输出，"
        "并添加必要的注释或步骤说明。绝不可使用上下文中未提及的外部最优解或超纲公式。\n"
        "7. 【忠实性与拒答红线】\n"
        "   - 允许归纳：你可以对上下文进行逻辑梳理、归纳总结和教学性解释，"
        "但所有核心事实、专业术语、数据和结论必须100%来源于提供的上下文。\n"
        "   - 严禁幻觉：绝不可引入上下文之外的预训练知识（如外部代码库、超纲考点）。\n"
        "   - 优雅拒答：如果上下文完全不足以回答该问题（即无法提取到任何与核心问题直接相关的事实），"
        "请不要生硬拒绝，必须使用以下标准句式回答：\"关于【此处复述用户的核心问题】，"
        "当前提供的参考资料中未包含足够的信息来解答，建议查阅相关教材的【推测所属章节】部分。\"\n"
        "8. 【学习路径类问题】如果问题涉及\"怎么学\"、\"怎么复习\"、\"学习路线\"、\"重点章节\"等学习方法，"
        "请按\"复习路线 → 重点章节 → 学习建议\"的结构组织答案，直接引用上下文中的路线和章节排序。"
    )),
    ("human", "【上下文】\n{context}\n\n【问题】{question}"),
])


def _resolve_eval_llm_config(
    model: str,
    api_base: str,
    api_key: str,
    settings_model: str,
    settings_api_base: str,
    settings_api_key: str,
) -> tuple[str, str, str]:
    """解析评估 LLM 配置链：cfg > EVAL_* settings > 全局 settings

    Args:
        model/api_base/api_key: EvaluationConfig 传入的覆盖值
        settings_model/api_base/api_key: settings 中 eval 专用的配置项

    Returns:
        (model, api_base, api_key) 三元组
    """
    resolved_model = model or settings_model or settings.LLM_MODEL
    resolved_base = api_base or settings_api_base or settings.LLM_API_BASE
    resolved_key = api_key or settings_api_key or settings.LLM_API_KEY
    return resolved_model, resolved_base, resolved_key


def _create_eval_llm(
    model: str,
    api_base: str,
    api_key: str,
    temperature: float = 0.0,
) -> ChatOpenAI:
    """创建评估专用的 ChatOpenAI 实例（不污染全局 settings/缓存）

    委托 llm_provider.create_llm() 构建，provider 专有参数统一管理。
    """
    return create_llm(
        model=model,
        api_base=api_base,
        api_key=api_key,
        temperature=temperature,
        streaming=False,
        timeout=120,
        max_retries=3,
    )


_answer_llm_cache: ChatOpenAI | None = None
_answer_llm_cache_key: tuple[str, str, str] = ("", "", "")


def _get_answer_llm(cfg: EvaluationConfig) -> ChatOpenAI:
    """获取答案生成 LLM（缓存实例，避免每次调用创建新对象）"""
    global _answer_llm_cache, _answer_llm_cache_key
    model, base, key = _resolve_eval_llm_config(
        cfg.answer_model, cfg.answer_api_base, cfg.answer_api_key,
        settings.EVAL_ANSWER_MODEL, settings.EVAL_ANSWER_API_BASE, settings.EVAL_ANSWER_API_KEY,
    )
    cache_key = (model, base, key)
    if _answer_llm_cache is not None and _answer_llm_cache_key == cache_key:
        return _answer_llm_cache
    logger.info("Eval answer LLM: model=%s base=%s", model, base)
    _answer_llm_cache = _create_eval_llm(model, base, key, temperature=0.3)
    _answer_llm_cache_key = cache_key
    return _answer_llm_cache



def _get_judge_llm_instructor(cfg: EvaluationConfig):
    """获取评测 LLM（自动选择最佳模式）

    DashScope (百炼): InstructorLLM 不兼容（content list 格式不支持），
        使用 LangchainLLMWrapper + Qwen 原生结构化输出能力。
    OpenAI / DeepSeek: 使用 InstructorLLM（function calling 强制结构化输出）。
    """
    model, base, key = _resolve_eval_llm_config(
        cfg.judge_model, cfg.judge_api_base, cfg.judge_api_key,
        settings.EVAL_JUDGE_MODEL, settings.EVAL_JUDGE_API_BASE, settings.EVAL_JUDGE_API_KEY,
    )

    # ── DashScope: LangchainLLMWrapper ──
    if detect_provider(base, model).is_dashscope:
        from ragas.llms import LangchainLLMWrapper
        logger.info("Eval judge LLM (LangchainLLMWrapper for DashScope): model=%s base=%s", model, base)
        lc_llm = _create_eval_llm(model, base, key, temperature=0.0)
        # DashScope 不支持 InstructorLLM（content list 格式），
        # LangchainLLMWrapper 靠 LLM 自行输出 JSON 再 pydantic 解析。
        # response_format=json_object 强制 Qwen 输出合法 JSON，
        # 避免 model_validate_json 解析失败 → NaN
        # 注意：必须合并而非覆盖 model_kwargs，保留 extra_body 中的 enable_thinking=False
        existing_kwargs = lc_llm.model_kwargs or {}
        existing_kwargs["response_format"] = {"type": "json_object"}
        lc_llm.model_kwargs = existing_kwargs
        return LangchainLLMWrapper(langchain_llm=lc_llm)

    # ── OpenAI / DeepSeek: InstructorLLM ──
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    logger.info("Eval judge LLM (InstructorLLM): model=%s base=%s", model, base)
    pc = detect_provider(base, model)
    default_headers = {}
    if pc.needs_thinking_disabled:
        default_headers["enable_thinking"] = "false"
    client = AsyncOpenAI(
        api_key=key,
        base_url=base,
        default_headers=default_headers or None,
    )
    llm = llm_factory(model, client=client)
    # 默认 max_tokens=1024 不够，function calling 响应常超 1024 tokens
    # 导致 finish_reason=length → instructor 解析失败 → 一直重试 → 卡住
    if llm.model_args is None:
        llm.model_args = {"max_tokens": 4096}
    elif isinstance(llm.model_args, dict):
        llm.model_args["max_tokens"] = 4096
    elif hasattr(llm.model_args, "max_tokens"):
        llm.model_args.max_tokens = 4096
    else:
        llm.model_args = {"max_tokens": 4096}
    return llm


def _normalize_content(content: Any) -> str:
    """归一化 LLM 返回的 content 为字符串

    DashScope 某些模型返回 [{"text": "..."}] 而非纯字符串。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content)


def _rewrite_query(query: str, collection_name: str, cfg: EvaluationConfig) -> str:
    """轻量 Query 改写：将短/模糊查询扩展为更丰富的表述，提升语义检索命中率。

    仅对短查询（<20 字）或概念型查询触发，长查询和代码查询跳过。
    使用 answer LLM 的快速模式，~50 tokens 输出，耗时 <1s。
    """
    # 跳过长查询/代码查询（它们本身足够具体）
    if len(query) > 30:
        return query
    code_indicators = ["代码", "实现", "程序", "code", "算法实现"]
    if any(p in query for p in code_indicators) and len(query) > 15:
        return query

    subject_hint = _SUBJECT_HINT.get(collection_name, "计算机科学")

    try:
        llm = _get_answer_llm(cfg)
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content=(
                f"你是一个查询改写助手，领域为{subject_hint}。"
                "将用户简短的查询扩展为更具体、更丰富的表述，"
                "补充关键术语和同义词，使语义检索能命中更多相关文档。\n"
                "规则：\n"
                "1. 保持原意不变，不添加查询未涉及的主题\n"
                "2. 补充该领域常见的同义术语（如'死锁'→'进程死锁 死锁预防 死锁避免'）\n"
                "3. 输出一行纯文本，不要解释，不要标点符号以外的格式\n"
                "4. 长度控制在 40 字以内"
            )),
            HumanMessage(content=f"原查询：{query}"),
        ]
        resp = llm.invoke(messages)
        rewritten = _normalize_content(resp.content).strip()
        if rewritten and len(rewritten) > len(query):
            logger.info("Query rewrite: '%s' → '%s'", query[:40], rewritten[:60])
            return rewritten
    except Exception as e:
        logger.debug("Query rewrite failed, using original: %s", e)
    return query


def retrieve_contexts(
    query: str,
    collection_name: str,
    cfg: EvaluationConfig,
    cross_subject_collections: list[str] | None = None,
) -> list[str]:
    """检索相关上下文（通过接口，与 RAG 实现解耦）

    Args:
        cross_subject_collections: 跨学科样本需搜索的多个 collection，
            如 ["operating_system", "computer_organization"]。
            非空时按 collection 分别检索并合并去重。
    """
    # ── Query 改写（短/概念查询 → 丰富表述，提升检索命中率）──
    effective_query = _rewrite_query(query, collection_name, cfg)

    retriever = get_retriever()

    # 评估场景不全局搜索 learning_paths：该集合仅含学习路线与重点章节，
    # 与大多数单科查询无关，引入噪声严重拉低 context_precision（AP 对排序敏感）
    # 学习路径类查询（怎么学/复习路线/重点章节）需搜索 learning_paths
    _LEARNING_PATH_INDICATORS = ("怎么学", "怎么复习", "学习路线", "学习路径", "复习路线",
                                  "复习路径", "重点章节", "如何学", "应该怎么学", "学习建议")
    is_cross_intent = (bool(cross_subject_collections) or
                       any(p in query for p in _CROSS_SUBJECT_INDICATORS))
    is_learning_path_query = any(p in query for p in _LEARNING_PATH_INDICATORS)
    always_search: list[str] = ["learning_paths"] if is_learning_path_query else []
    primary_collections = [collection_name] if collection_name and collection_name in _VALID_COLLECTIONS else []
    if cross_subject_collections:
        primary_collections.extend(c for c in cross_subject_collections if c in _VALID_COLLECTIONS)
    all_search_cols = primary_collections + [c for c in always_search if c not in primary_collections]

    # 统一走多 collection 检索逻辑
    all_contents: list[str] = []
    all_docs_with_meta: list[dict[str, Any]] = []  # {content, rerank_score, is_window_expanded}
    seen: set[str] = set()
    per_col_k = max(cfg.retrieval_k // max(len(all_search_cols), 1), 2)
    for col in all_search_cols:
        try:
            docs = retriever.retrieve(
                query=effective_query,
                collection_name=col,
                k=per_col_k,
                use_rerank=cfg.use_rerank,
            )
            for d in docs:
                content = d["content"]
                if content not in seen:
                    seen.add(content)
                    meta = d.get("metadata", {}) or {}
                    rerank_score = float(meta.get("rerank_score", 0) or 0)
                    # window expansion 新增的 chunk 没有 rerank_score（=0），
                    # 但有 _window_expanded 标记，对 recall 有贡献
                    is_window = bool(meta.get("_window_expanded"))
                    all_docs_with_meta.append({
                        "content": content,
                        "rerank_score": rerank_score,
                        "is_window": is_window,
                    })
        except Exception as e:
            logger.warning("Retrieve failed for collection %s: %s", col, e)

    # ── 排序策略（对 AP 至关重要）──
    # AP 公式对 context 顺序敏感：相关 context 必须排在前面
    # 排序优先级：
    #   1. 有 rerank_score > 0 的文档（按 score 降序）—— reranker 判定相关
    #   2. window expansion 文档（score=0 但有 _window_expanded 标记）—— 相邻 chunk，辅助 recall
    #   3. score=0 且非 window 的文档（rerank fallback 噪声）—— 排最后
    def _sort_key(item: dict) -> tuple:
        score = item["rerank_score"]
        is_window = item["is_window"]
        # 三层排序：有score > 无score+window > 无score+非window
        tier = 0 if score > 0 else (1 if is_window else 2)
        return (tier, -score)  # tier 升序，score 降序（用负数）

    all_docs_with_meta.sort(key=_sort_key)

    # 最终截断：确保不超过 retrieval_k
    if len(all_docs_with_meta) > cfg.retrieval_k:
        all_docs_with_meta = all_docs_with_meta[:cfg.retrieval_k]

    all_contents = [d["content"] for d in all_docs_with_meta]
    n_reranked = sum(1 for d in all_docs_with_meta if d["rerank_score"] > 0)
    n_window = sum(1 for d in all_docs_with_meta if d["is_window"])
    n_noise = len(all_docs_with_meta) - n_reranked - n_window
    logger.info(
        "Eval retrieve: query=%s total=%d (reranked=%d, window=%d, noise=%d)",
        query[:40], len(all_contents), n_reranked, n_window, n_noise,
    )
    return all_contents


# 答案缓存：避免重复评估时重生成，节省 token
_answer_cache: dict[str, str] = {}
_ANSWER_CACHE_MAX = 500

# Token 消耗统计
_token_counter: dict[str, int] = {
    "answer_input": 0, "answer_output": 0, "answer_calls": 0,
    "cache_hits": 0, "empty_context_skips": 0,
}

# 上下文 token 预算（粗估：中文×1.5 + ASCII×0.25）
_CONTEXT_TOKEN_BUDGET = 12000


def _truncate_contexts(contexts: list[str], budget: int = _CONTEXT_TOKEN_BUDGET) -> list[str]:
    """按 token 预算截断上下文，避免全量灌入 LLM"""
    result: list[str] = []
    used = 0
    for ctx in contexts:
        t = _estimate_tokens(ctx)
        if used + t > budget:
            # 截断当前 context 到剩余预算
            remaining = budget - used
            if remaining > 100:
                # 按 token 比例估算字符截断位置
                char_budget = int(len(ctx) * remaining / max(t, 1))
                result.append(ctx[:char_budget] + "...")
            break
        result.append(ctx)
        used += t
    return result


def _answer_cache_key(query: str, contexts: list[str]) -> str:
    """答案缓存 key：query + contexts 摘要"""
    import hashlib
    ctx_hash = hashlib.md5("||".join(contexts).encode()).hexdigest()[:8]
    return f"{query}::{ctx_hash}"


def generate_answer(query: str, contexts: list[str], cfg: EvaluationConfig, use_cache: bool = True) -> str:
    """基于上下文生成答案（带缓存 + 上下文截断）"""
    # 缓存命中
    cache_key = _answer_cache_key(query, contexts) if use_cache else ""
    if cache_key and cache_key in _answer_cache:
        _token_counter["cache_hits"] += 1
        return _answer_cache[cache_key]

    # 截断上下文
    truncated = _truncate_contexts(contexts)
    context_text = "\n\n".join(truncated)
    llm = _get_answer_llm(cfg)
    messages = _ANSWER_PROMPT.format_messages(question=query, context=context_text)
    response = llm.invoke(messages)
    answer = _normalize_content(response.content)

    # Token 统计
    _token_counter["answer_input"] += _estimate_tokens(context_text) + _estimate_tokens(query)
    _token_counter["answer_output"] += _estimate_tokens(answer)
    _token_counter["answer_calls"] += 1

    # 写入缓存
    if cache_key:
        if len(_answer_cache) >= _ANSWER_CACHE_MAX:
            _answer_cache.clear()
        _answer_cache[cache_key] = answer

    return answer


def run_ragas_evaluation(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """执行 RAGAS 评估

    流程：
    1. 对每条样本：检索上下文 → 生成答案
    2. 用 RAGAS 原生指标 + judge LLM 计算分数
    3. 聚合输出

    Returns:
        {"faithfulness": {mean, std, p50, p90, ...},
         "context_precision": {...},
         "context_recall": {...},
         "answer_relevancy": {...},
         "_meta": {...}}
    """
    start = time.perf_counter()
    ragas_records: list[dict[str, Any]] = []

    # 重置计数器（防止上次异常中断导致脏数据）
    _token_counter.update({"answer_input": 0, "answer_output": 0, "answer_calls": 0,
                           "cache_hits": 0, "empty_context_skips": 0})

    skipped = 0
    refusal_indices: list[int] = []  # 拒答样本在 ragas_records 中的索引
    record_sample_indices: list[int] = []  # ragas_records[i] 对应的 samples 索引

    # 学习路径类查询由 path_agent（KG + learning_paths 集合）处理，
    # 不走知识问答 RAG 管线，纳入 RAGAS 评估会不公平地拉低分数
    _LP_INDICATORS = ("怎么学", "怎么复习", "学习路线", "学习路径", "复习路线",
                      "复习路径", "重点章节", "如何学", "应该怎么学", "学习建议",
                      "前置知识")

    for idx, sample in enumerate(samples):
        logger.info("RAGAS [%d/%d] %s", idx + 1, len(samples), sample.query[:60])

        # 跳过学习路径类查询（由 path_agent 处理，不属于知识问答 RAG 管线）
        if any(p in sample.query for p in _LP_INDICATORS):
            logger.info("RAGAS [%d/%d] 跳过学习路径查询: %s", idx + 1, len(samples), sample.query[:40])
            skipped += 1
            continue

        # 检索上下文（如果未预置）
        if not sample.contexts:
            try:
                # 跨学科样本：从 metadata.cross_subject 提取多集合
                cross_cols = None
                cs_raw = sample.metadata.get("cross_subject", "")
                if cs_raw:
                    cross_cols = [c.strip() for c in cs_raw.split(",") if c.strip()]
                # 每个样本使用自己的 category 作为检索集合
                # （baseline.jsonl 包含多学科，全局 collection_name 不适用）
                sample_collection = sample.metadata.get("category", collection_name) or collection_name
                contexts = retrieve_contexts(
                    sample.query, sample_collection, cfg,
                    cross_subject_collections=cross_cols,
                )
            except Exception as e:
                logger.warning("RAGAS [%d/%d] 检索失败，跳过: %s", idx + 1, len(samples), e)
                skipped += 1
                continue
        else:
            contexts = sample.contexts

        # 空 context 检测：跳过 LLM 调用，避免生成废话浪费 token
        has_valid_context = bool(contexts) and any(c.strip() for c in contexts)

        # 生成答案（如果未预置）
        if not sample.answer and has_valid_context:
            try:
                answer = generate_answer(sample.query, contexts, cfg)
            except Exception as e:
                logger.warning("RAGAS [%d/%d] 答案生成失败: %s", idx + 1, len(samples), e)
                answer = ""
        elif sample.answer:
            answer = sample.answer
        else:
            answer = ""

        if not has_valid_context and not answer:
            logger.info("RAGAS [%d/%d] 空 context 且无预置答案，跳过", idx + 1, len(samples))
            _token_counter["empty_context_skips"] += 1
            skipped += 1
            continue

        record = sample.to_ragas_dict()
        record["retrieved_contexts"] = contexts
        record["response"] = answer
        ragas_records.append(record)
        record_sample_indices.append(idx)  # 记录 ragas_records[-1] 对应 samples[idx]

        # ── 拒答检测 ──
        # RAGAS answer_relevancy 的 noncommittal 检测对中文拒答不敏感
        # （"根据提供的上下文无法回答" 可能不被判定为 noncommittal=1）
        # 此处标记拒答样本，在聚合时单独统计拒答率和 answer_relevancy 修正
        is_refusal = any(p in answer for p in _REFUSAL_PATTERNS)
        if is_refusal:
            refusal_indices.append(len(ragas_records) - 1)  # 当前记录的索引
            logger.info("RAGAS [%d/%d] 检测到拒答: %s", idx + 1, len(samples), answer[:60])

    if skipped:
        logger.warning("RAGAS: 跳过 %d/%d 条样本（检索失败）", skipped, len(samples))

    if not ragas_records:
        return {}

    # ── RAGAS 原生计算 ──
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import (
        faithfulness,
        context_precision,
        context_recall,
        answer_relevancy,
    )

    # 兜底补全缺失字段（Qwen3.6 输出 {"verdict":"0"} 缺 reason → NaN）
    _patch_ragas_json_fallback()

    dataset = Dataset.from_list(ragas_records)

    # 配置 judge LLM：自动选择最佳模式
    # DashScope → LangchainLLMWrapper（InstructorLLM 不兼容 content list 格式）
    # OpenAI/DeepSeek → InstructorLLM（function calling 强制结构化输出）
    judge_llm = _get_judge_llm_instructor(cfg)

    # 选择启用的指标
    # answer_relevancy: strictness=1 避免多次生成导致的不稳定
    # context_precision/recall: max_retries=3 提高结构化输出稳定性
    answer_relevancy.strictness = 1
    context_precision.max_retries = 3
    context_recall.max_retries = 3

    metric_map = {
        "faithfulness": faithfulness,
        "context_precision": context_precision,
        "context_recall": context_recall,
        "answer_relevancy": answer_relevancy,
    }
    metrics_to_compute = [
        metric_map[name] for name in cfg.ragas_metrics if name in metric_map
    ]

    # 将 judge LLM 直接设置到每个指标上
    # （ragas_evaluate 内部也会设置，但显式设置确保类型正确）
    # DashScope 用 LangchainLLMWrapper，其他用 InstructorLLM
    for metric in metrics_to_compute:
        metric.llm = judge_llm

    if not metrics_to_compute:
        logger.warning("没有启用的 RAGAS 指标")
        return {"_meta": {"n": len(ragas_records), "error": "no metrics enabled"}}

    # 获取 embedding（仅 answer_relevancy 需要）
    # 使用 LangChain OpenAIEmbeddings 对接 TEI，带重试避免 500 错误
    lc_embeddings = None
    if "answer_relevancy" in cfg.ragas_metrics:
        try:
            from langchain_openai import OpenAIEmbeddings
            lc_embeddings = OpenAIEmbeddings(
                api_key=settings.EMBEDDING_API_KEY,
                base_url=settings.EMBEDDING_API_BASE,
                model=settings.EMBEDDING_MODEL,
                max_retries=5,
                request_timeout=60,
                check_embedding_ctx_length=False,
            )
        except Exception as e:
            logger.warning("Embedding 初始化失败，跳过 answer_relevancy: %s", e)
            metrics_to_compute = [m for m in metrics_to_compute if m != answer_relevancy]
            if not metrics_to_compute:
                return {"_meta": {"n": len(ragas_records), "error": f"embedding init failed: {e}"}}

    # RunConfig: 设置超时和重试
    # context_precision 需要对每个 context 片段逐一判断，调用次数多
    # timeout=300 确保单次 LLM 调用有足够时间完成结构化输出
    run_config = RunConfig(timeout=300, max_retries=3, max_wait=60)

    try:
        # llm=judge_llm: DashScope 用 LangchainLLMWrapper，其他用 InstructorLLM
        # RAGAS 会根据类型自动选择调用路径
        ragas_result = ragas_evaluate(
            dataset,
            metrics=metrics_to_compute,
            llm=judge_llm,
            embeddings=lc_embeddings,
            run_config=run_config,
            raise_exceptions=False,
            show_progress=True,
        )
    except Exception as e:
        logger.error("RAGAS evaluate 失败: %s", e)
        return {"_meta": {"n": len(ragas_records), "error": str(e)}}

    # NaN 诊断：输出每条样本的原始分数用于排查
    # RAGAS 0.4.x EvaluationResult: __getitem__(metric_name) 返回 list[float]
    # _scores_dict 是私有属性但稳定（__post_init__ 中设置），用 getattr 做防御性访问
    result_scores = getattr(ragas_result, "_scores_dict", None)
    if result_scores is None:
        # Fallback: 逐指标用公共 API 提取
        result_scores = {}
        for m_name in cfg.ragas_metrics:
            if m_name in metric_map:
                try:
                    result_scores[m_name] = ragas_result[m_name]
                except (KeyError, TypeError):
                    pass

    # 记录实际使用的模型配置（提前解析，供 NaN 诊断和 _meta 使用）
    judge_model_name, judge_base, _ = _resolve_eval_llm_config(
        cfg.judge_model, cfg.judge_api_base, cfg.judge_api_key,
        settings.EVAL_JUDGE_MODEL, settings.EVAL_JUDGE_API_BASE, settings.EVAL_JUDGE_API_KEY,
    )
    answer_model_name, answer_base, _ = _resolve_eval_llm_config(
        cfg.answer_model, cfg.answer_api_base, cfg.answer_api_key,
        settings.EVAL_ANSWER_MODEL, settings.EVAL_ANSWER_API_BASE, settings.EVAL_ANSWER_API_KEY,
    )

    nan_metrics = []
    for metric_name in cfg.ragas_metrics:
        if metric_name in metric_map and metric_name in result_scores:
            vals = [float(s) for s in result_scores[metric_name]]
            nan_count = sum(1 for v in vals if isinstance(v, float) and math.isnan(v))
            if nan_count > 0:
                nan_metrics.append(f"{metric_name}={nan_count}/{len(vals)} NaN")
    if nan_metrics:
        logger.warning("RAGAS NaN detected: %s — judge model may be incompatible (model=%s base=%s)",
                       ", ".join(nan_metrics), judge_model_name, judge_base)

    # ── 聚合结果（单次遍历，同时计算统计 + 附加 raw_scores）──
    aggregated: dict[str, dict[str, Any]] = {}

    for metric_name in cfg.ragas_metrics:
        if metric_name not in metric_map:
            continue
        try:
            # 优先从 _scores_dict 取，否则用公共 __getitem__ API
            if isinstance(result_scores, dict) and metric_name in result_scores:
                scores = result_scores[metric_name]
            else:
                scores = ragas_result[metric_name]
            vals = [float(s) for s in scores]
            aggregated[metric_name] = _aggregate_scores(vals)
            aggregated[metric_name]["raw_scores"] = vals
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("无法读取指标 %s: %s", metric_name, e)

    # ── 按学科分组统计 ──
    # 全局均值会被学科分布偏差扭曲（如 OS 占 30% 而 CN 只占 17.5%）
    # 按学科分组统计能暴露某个学科检索质量差的问题
    category_indices: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(ragas_records):
        # 用 record_sample_indices 正确映射：ragas_records[i] → samples[record_sample_indices[i]]
        sample_idx = record_sample_indices[i] if i < len(record_sample_indices) else -1
        cat = samples[sample_idx].metadata.get("category", "unknown") if 0 <= sample_idx < len(samples) else "unknown"
        category_indices[cat].append(i)

    per_category: dict[str, dict[str, dict[str, float]]] = {}
    for cat, indices in sorted(category_indices.items()):
        per_category[cat] = {}
        for metric_name in cfg.ragas_metrics:
            if metric_name not in aggregated:
                continue
            raw = aggregated[metric_name].get("raw_scores", [])
            cat_scores = [raw[i] for i in indices if i < len(raw)
                          and not (isinstance(raw[i], float) and math.isnan(raw[i]))]
            if cat_scores:
                per_category[cat][metric_name] = {
                    "mean": round(sum(cat_scores) / len(cat_scores), 4),
                    "n": len(cat_scores),
                }
    if per_category:
        aggregated["_per_category"] = per_category

    # ── answer_relevancy 拒答修正 ──
    # 拒答样本的 answer_relevancy 不应计入均值（拒答是检索失败的后果，
    # 不是模型相关性差），单独统计拒答率和可回答样本的相关性
    ar_key = "answer_relevancy"
    refusal_stats: dict[str, Any] = {}
    if refusal_indices and ar_key in aggregated:
        ar_raw = aggregated[ar_key].get("raw_scores", [])
        refusal_ar_scores = [ar_raw[i] for i in refusal_indices if i < len(ar_raw)]
        answerable_ar_scores = [ar_raw[i] for i in range(len(ar_raw))
                                if i not in set(refusal_indices) and i < len(ar_raw)
                                and not (isinstance(ar_raw[i], float) and math.isnan(ar_raw[i]))]
        refusal_stats = {
            "refusal_count": len(refusal_indices),
            "refusal_rate": round(len(refusal_indices) / max(len(ragas_records), 1), 4),
            "refusal_ar_mean": round(sum(refusal_ar_scores) / max(len(refusal_ar_scores), 1), 4)
                if refusal_ar_scores else None,
            "answerable_ar_mean": round(sum(answerable_ar_scores) / max(len(answerable_ar_scores), 1), 4)
                if answerable_ar_scores else None,
            "answerable_n": len(answerable_ar_scores),
        }
        # 修正 answer_relevancy 均值：只算可回答样本
        if answerable_ar_scores:
            aggregated[ar_key]["mean_answerable_only"] = refusal_stats["answerable_ar_mean"]
            logger.info(
                "answer_relevancy 拒答修正: refusal=%d/%d, refusal_ar_mean=%s, answerable_ar_mean=%.4f",
                len(refusal_indices), len(ragas_records),
                refusal_stats.get("refusal_ar_mean", "N/A"),
                refusal_stats["answerable_ar_mean"],
            )

    aggregated["_meta"] = {
        "n": len(ragas_records),
        "duration_ms": round((time.perf_counter() - start) * 1000, 3),
        "judge_model": judge_model_name,
        "judge_api_base": judge_base,
        "answer_model": answer_model_name,
        "answer_api_base": answer_base,
        "skipped": skipped,
        "refusal": refusal_stats if refusal_stats else {
            "refusal_count": len(refusal_indices),
            "refusal_rate": round(len(refusal_indices) / max(len(ragas_records), 1), 4),
        },
        "token_stats": {
            "answer_input_est": _token_counter["answer_input"],
            "answer_output_est": _token_counter["answer_output"],
            "answer_llm_calls": _token_counter["answer_calls"],
            "cache_hits": _token_counter["cache_hits"],
            "empty_context_skips": _token_counter["empty_context_skips"],
            # RAGAS judge LLM token 粗估：每条样本每指标 ~2K input + ~300 output
            "judge_input_est": len(ragas_records) * len(metrics_to_compute) * 2000,
            "judge_output_est": len(ragas_records) * len(metrics_to_compute) * 300,
        },
    }

    return aggregated


def _aggregate_scores(scores: list[float]) -> dict[str, float | int]:
    """对分数列表做聚合统计（自动过滤 NaN）"""
    if not scores:
        return {}
    # 过滤 NaN：一粒老鼠屎不坏一锅汤
    nan_count = sum(1 for s in scores if isinstance(s, float) and math.isnan(s))
    valid_scores = [s for s in scores if not (isinstance(s, float) and math.isnan(s))]
    if not valid_scores:
        return {"mean": float('nan'), "n": len(scores), "nan_count": nan_count}
    sorted_scores = sorted(valid_scores)
    n = len(sorted_scores)
    mean_val = sum(sorted_scores) / n
    variance = sum((s - mean_val) ** 2 for s in sorted_scores) / n
    # 小样本分位数修正：n<10 时 p90 退化为 max，改用插值
    def _percentile(vals: list[float], p: float) -> float:
        if len(vals) <= 1:
            return vals[0]
        k = (len(vals) - 1) * p
        f_idx = int(k)
        c_idx = min(f_idx + 1, len(vals) - 1)
        frac = k - f_idx
        return vals[f_idx] + frac * (vals[c_idx] - vals[f_idx])
    return {
        "mean": round(mean_val, 4),
        "std": round(variance ** 0.5, 4) if n > 1 else 0.0,
        "min": round(sorted_scores[0], 4),
        "max": round(sorted_scores[-1], 4),
        "p50": round(_percentile(sorted_scores, 0.5), 4),
        "p90": round(_percentile(sorted_scores, 0.9), 4),
        "n": len(scores),
        "valid_n": n,
        "nan_count": nan_count,
    }
