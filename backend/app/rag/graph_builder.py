"""LLM 自动构建知识图谱模块

从文档内容中自动抽取知识点和关系，写入 Neo4j 知识图谱。
在 ETL pipeline 中，enhance_documents 之后、add_documents 之前调用。

抽取策略：
1. 将文档 chunk 按 batch 发送给 LLM
2. LLM 按指定 JSON Schema 输出知识点和关系
3. 解析 LLM 输出，写入知识图谱
4. 失败时静默降级，不影响主流程
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.documents import Document

from app.rag.rag_utils import get_llm
from app.rag.schemas import KGExtractResult
from app.rag.rag_utils import estimate_tokens as _estimate_tokens
logger = logging.getLogger(__name__)

# 每次 LLM 调用处理的 chunk 数量
_BATCH_SIZE = 10
_MAX_BATCH_TOKENS = 6000  # 每 batch token 预算上限（替代硬截断 content[:6000]）
_MAX_RETRIES = 2  # 截断重试次数

# LLM 抽取 prompt（structured output 用）
_EXTRACT_PROMPT = """你是一个知识图谱构建助手。请从以下文本中提取知识点和它们之间的关系。

要求：
1. 提取所有重要的知识点（概念、技术、方法等）
2. 识别知识点之间的前置依赖关系（PREREQUISITE_OF）和关联关系（RELATED_TO）
3. 每个知识点需要名称(name)和简短描述(description)
4. 关系类型只有两种：PREREQUISITE_OF（前置知识）和 RELATED_TO（相关知识）
5. 输出必须是合法 json，顶层字段必须是 nodes 和 edges

文本内容：
{content}"""

# Plain JSON fallback prompt（强制只输出 JSON）
_JSON_FALLBACK_PROMPT = """请从以下文本中提取知识点和关系，只输出合法 json，不要任何解释或 markdown 代码块。
json 顶层字段为 nodes 和 edges：
- nodes: 数组，每个元素 {{"name":"知识点","description":"简短描述"}}
- edges: 数组，每个元素 {{"source":"前置/来源","target":"后续/目标","relation":"PREREQUISITE_OF 或 RELATED_TO"}}

只从给定文本提取，不要编造。如果文本无知识点，输出 {{"nodes":[],"edges":[]}}

文本：
{content}"""


def _truncate_to_token_budget(text: str, budget: int) -> str:
    """按 token 预算截断文本，替代硬编码 content[:6000]"""
    if _estimate_tokens(text) <= budget:
        return text
    # 按 token/char 比例估算截断位置
    ratio = budget / max(_estimate_tokens(text), 1)
    char_budget = int(len(text) * ratio)
    return text[:char_budget]


def _coerce_kg_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"nodes": [], "edges": []}

    raw_nodes = payload.get("nodes") or payload.get("entities") or payload.get("concepts") or []
    raw_edges = payload.get("edges") or payload.get("relations") or payload.get("relationships") or []

    nodes: list[dict[str, str]] = []
    for item in raw_nodes if isinstance(raw_nodes, list) else []:
        if isinstance(item, str):
            name = item.strip()
            desc = ""
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("entity") or item.get("concept") or item.get("title") or "").strip()
            desc = str(item.get("description") or item.get("desc") or "").strip()
        else:
            continue
        if name:
            nodes.append({"name": name, "description": desc})

    edges: list[dict[str, str]] = []
    for item in raw_edges if isinstance(raw_edges, list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or item.get("from") or item.get("head") or item.get("start") or "").strip()
        target = str(item.get("target") or item.get("to") or item.get("tail") or item.get("end") or "").strip()
        relation = str(item.get("relation") or item.get("type") or "RELATED_TO").strip()
        if relation not in {"PREREQUISITE_OF", "RELATED_TO"}:
            relation = "RELATED_TO"
        if source and target:
            edges.append({"source": source, "target": target, "relation": relation})

    return {"nodes": nodes, "edges": edges}


def _coerce_from_exception(exc: Exception) -> dict[str, Any] | None:
    """从 Pydantic ValidationError 中抢救 LLM 返回的不合规 payload"""
    if not hasattr(exc, "errors"):
        return None
    try:
        all_nodes: list[dict[str, str]] = []
        all_edges: list[dict[str, str]] = []
        for err in exc.errors():
            payload = err.get("input")
            if not isinstance(payload, dict):
                continue
            # 单个 edge dict（含 source/target/type 但缺 relation）
            if ("source" in payload or "from" in payload) and ("target" in payload or "to" in payload):
                source = str(payload.get("source") or payload.get("from") or payload.get("head") or payload.get("start") or "").strip()
                target = str(payload.get("target") or payload.get("to") or payload.get("tail") or payload.get("end") or "").strip()
                relation = str(payload.get("relation") or payload.get("type") or "RELATED_TO").strip()
                if relation not in {"PREREQUISITE_OF", "RELATED_TO"}:
                    relation = "RELATED_TO"
                if source and target:
                    all_edges.append({"source": source, "target": target, "relation": relation})
            # 单个 node dict
            elif "name" in payload or "entity" in payload or "concept" in payload:
                name = str(payload.get("name") or payload.get("entity") or payload.get("concept") or payload.get("title") or "").strip()
                desc = str(payload.get("description") or payload.get("desc") or "").strip()
                if name:
                    all_nodes.append({"name": name, "description": desc})
            # 整体 payload（含 nodes/edges 或 entities/relations）
            else:
                coerced = _coerce_kg_payload(payload)
                all_nodes.extend(coerced["nodes"])
                all_edges.extend(coerced["edges"])
        # 去重
        seen_nodes = {(n["name"], n["description"]) for n in all_nodes}
        deduped_nodes = [n for n in all_nodes if (n["name"], n["description"]) in seen_nodes and not seen_nodes.discard((n["name"], n["description"]))]
        seen_edges = {(e["source"], e["target"], e["relation"]) for e in all_edges}
        deduped_edges = [e for e in all_edges if (e["source"], e["target"], e["relation"]) in seen_edges and not seen_edges.discard((e["source"], e["target"], e["relation"]))]
        if deduped_nodes or deduped_edges:
            return {"nodes": deduped_nodes, "edges": deduped_edges}
    except Exception:
        return None
    return None


def _extract_with_structured_output(content: str, retry_on_empty: bool = True) -> dict[str, Any]:
    """结构化 KG 抽取：with_structured_output(KGExtractResult) + 截断重试"""
    llm = get_llm()
    structured_llm = llm.with_structured_output(KGExtractResult)
    truncated = _truncate_to_token_budget(content, _MAX_BATCH_TOKENS)
    prompt = _EXTRACT_PROMPT.format(content=truncated)

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = structured_llm.invoke(prompt)
            if result.nodes or result.edges:
                return {"nodes": [n.model_dump() for n in result.nodes], "edges": [e.model_dump() for e in result.edges]}
            # 空结果：可能是输入过长导致输出截断，缩小输入重试
            if retry_on_empty and attempt < _MAX_RETRIES:
                budget = _MAX_BATCH_TOKENS // (2 ** (attempt + 1))
                truncated = _truncate_to_token_budget(content, budget)
                prompt = _EXTRACT_PROMPT.format(content=truncated)
                logger.info("KG extract empty result, retry with budget=%d (attempt %d)", budget, attempt + 1)
                continue
            return {"nodes": [], "edges": []}
        except Exception as e:
            coerced = _coerce_from_exception(e)
            if coerced:
                return coerced
            logger.warning("KG structured extraction failed (attempt %d): %s", attempt + 1, e)
            if attempt < _MAX_RETRIES:
                budget = _MAX_BATCH_TOKENS // (2 ** (attempt + 1))
                truncated = _truncate_to_token_budget(content, budget)
                prompt = _EXTRACT_PROMPT.format(content=truncated)
                continue
            return {"nodes": [], "edges": []}
    return {"nodes": [], "edges": []}


async def _aextract_with_structured_output(content: str, retry_on_empty: bool = True) -> dict[str, Any]:
    """异步结构化 KG 抽取"""
    llm = get_llm()
    structured_llm = llm.with_structured_output(KGExtractResult)
    truncated = _truncate_to_token_budget(content, _MAX_BATCH_TOKENS)
    prompt = _EXTRACT_PROMPT.format(content=truncated)

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = await structured_llm.ainvoke(prompt)
            if result.nodes or result.edges:
                return {"nodes": [n.model_dump() for n in result.nodes], "edges": [e.model_dump() for e in result.edges]}
            if retry_on_empty and attempt < _MAX_RETRIES:
                budget = _MAX_BATCH_TOKENS // (2 ** (attempt + 1))
                truncated = _truncate_to_token_budget(content, budget)
                prompt = _EXTRACT_PROMPT.format(content=truncated)
                logger.info("KG extract empty result, retry with budget=%d (attempt %d)", budget, attempt + 1)
                continue
            return {"nodes": [], "edges": []}
        except Exception as e:
            coerced = _coerce_from_exception(e)
            if coerced:
                return coerced
            logger.warning("KG structured extraction failed (attempt %d): %s", attempt + 1, e)
            if attempt < _MAX_RETRIES:
                budget = _MAX_BATCH_TOKENS // (2 ** (attempt + 1))
                truncated = _truncate_to_token_budget(content, budget)
                prompt = _EXTRACT_PROMPT.format(content=truncated)
                continue
            return {"nodes": [], "edges": []}
    return {"nodes": [], "edges": []}


def _extract_via_json_fallback(content: str) -> dict[str, Any]:
    """Plain JSON fallback：普通 LLM 调用 + 手动 JSON 解析"""
    llm = get_llm(streaming=False, temperature=0.0)
    truncated = _truncate_to_token_budget(content, _MAX_BATCH_TOKENS)
    prompt = _JSON_FALLBACK_PROMPT.format(content=truncated)
    try:
        raw = llm.invoke(prompt)
        text = str(raw.content if hasattr(raw, "content") else raw).strip()
        # 去除 markdown 代码块包裹
        if text.startswith("```"):
            first_nl = text.find("\n")
            text = text[first_nl + 1:] if first_nl >= 0 else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return {"nodes": [], "edges": []}
        parsed = json.loads(text[start:end])
        return _coerce_kg_payload(parsed)
    except Exception as e:
        logger.warning("KG JSON fallback failed: %s", e)
        return {"nodes": [], "edges": []}


def extract_knowledge_from_text(content: str) -> dict[str, Any]:
    """从文本中提取知识点和关系（同步，先 structured output，空则 fallback）

    Returns:
        {"nodes": [...], "edges": [...]}
    """
    result = _extract_with_structured_output(content)
    if result.get("nodes") or result.get("edges"):
        return result
    # structured output 返回空，尝试 plain JSON fallback
    logger.info("KG structured output empty, trying JSON fallback")
    return _extract_via_json_fallback(content)


async def aextract_knowledge_from_text(content: str) -> dict[str, Any]:
    """从文本中提取知识点和关系（异步，先 structured output，空则 fallback）"""
    result = await _aextract_with_structured_output(content)
    if result.get("nodes") or result.get("edges"):
        return result
    logger.info("KG async structured output empty, trying JSON fallback")
    return _extract_via_json_fallback(content)


def build_graph_from_documents(
    documents: list[Document],
    category: str = "data_structure",
    batch_size: int = _BATCH_SIZE,
    source_file: str = "",
) -> dict:
    """从文档列表自动构建知识图谱

    将文档按 batch 发送给 LLM 抽取知识点和关系，然后写入 Neo4j。

    Args:
        documents: 已分块的文档列表
        category: 知识点分类
        batch_size: 每次 LLM 调用处理的 chunk 数
        source_file: 来源文件名（用于溯源和一致性管理）
    """
    from app.rag.knowledge_graph import get_kg_manager

    kg_manager = get_kg_manager()
    if not documents:
        return {"nodes_added": 0, "edges_added": 0, "errors": 0}

    total_nodes = 0
    total_edges = 0
    errors = 0
    total_batches = (len(documents) + batch_size - 1) // batch_size

    for i in range(0, len(documents), batch_size):
        batch_idx = i // batch_size + 1
        batch = documents[i:i + batch_size]
        # 拼接 batch 内的 chunk 内容
        combined = "\n\n---\n\n".join(doc.page_content for doc in batch)

        print(f"    [KG] 批次 {batch_idx}/{total_batches} ({source_file}) LLM 抽取中...", end="", flush=True)
        result = extract_knowledge_from_text(combined)
        n_nodes = len(result.get("nodes", []))
        n_edges = len(result.get("edges", []))
        print(f" → {n_nodes} 节点, {n_edges} 关系", flush=True)

        nodes = result.get("nodes", [])
        edges = result.get("edges", [])

        if not nodes and not edges:
            continue

        # 写入知识图谱
        try:
            # 添加节点
            for node in nodes:
                name = node.get("name", "").strip()
                desc = node.get("description", "").strip()
                if name:
                    kg_manager.add_knowledge_node(
                        name=name,
                        category=category,
                        description=desc,
                        source_file=source_file,
                    )
                    total_nodes += 1

            # 添加关系
            for edge in edges:
                source = edge.get("source", "").strip()
                target = edge.get("target", "").strip()
                relation = edge.get("relation", "RELATED_TO").strip()
                if source and target:
                    if relation == "PREREQUISITE_OF":
                        kg_manager.add_prerequisite(source, target)
                    else:
                        kg_manager.add_related(source, target)
                    total_edges += 1

        except Exception as e:
            logger.warning("Failed to write graph data: %s", e)
            errors += 1

    logger.info(
        "Graph build completed: nodes=%d edges=%d errors=%d",
        total_nodes, total_edges, errors,
    )

    return {
        "nodes_added": total_nodes,
        "edges_added": total_edges,
        "errors": errors,
    }


async def abuild_graph_from_documents(
    documents: list[Document],
    category: str = "data_structure",
    batch_size: int = _BATCH_SIZE,
    source_file: str = "",
) -> dict:
    """从文档列表自动构建知识图谱（异步）

    Args:
        documents: 已分块的文档列表
        category: 知识点分类
        batch_size: 每次 LLM 调用处理的 chunk 数
        source_file: 来源文件名（用于溯源和一致性管理）
    """
    import asyncio
    from app.rag.knowledge_graph import get_kg_manager

    kg_manager = get_kg_manager()

    total_nodes = 0
    total_edges = 0
    errors = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        combined = "\n\n---\n\n".join(doc.page_content for doc in batch)

        result = await aextract_knowledge_from_text(combined)

        nodes = result.get("nodes", [])
        edges = result.get("edges", [])

        if not nodes and not edges:
            continue

        try:
            # 写入图谱（同步操作，用 to_thread 包裹）
            def _write_graph():
                n, e = 0, 0
                for node in nodes:
                    name = node.get("name", "").strip()
                    desc = node.get("description", "").strip()
                    if name:
                        kg_manager.add_knowledge_node(
                            name=name, category=category, description=desc,
                            source_file=source_file,
                        )
                        n += 1
                for edge in edges:
                    source = edge.get("source", "").strip()
                    target = edge.get("target", "").strip()
                    relation = edge.get("relation", "RELATED_TO").strip()
                    if source and target:
                        if relation == "PREREQUISITE_OF":
                            kg_manager.add_prerequisite(source, target)
                        else:
                            kg_manager.add_related(source, target)
                        e += 1
                return n, e

            n, e = await asyncio.to_thread(_write_graph)
            total_nodes += n
            total_edges += e

        except Exception as e:
            logger.warning("Failed to write graph data: %s", e)
            errors += 1

    logger.info(
        "Graph build completed: nodes=%d edges=%d errors=%d",
        total_nodes, total_edges, errors,
    )

    return {
        "nodes_added": total_nodes,
        "edges_added": total_edges,
        "errors": errors,
    }
