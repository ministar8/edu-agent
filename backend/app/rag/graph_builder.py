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
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.rag.retriever import get_llm
logger = logging.getLogger(__name__)

# 每次 LLM 调用处理的 chunk 数量
_BATCH_SIZE = 5

# LLM 抽取 prompt
_EXTRACT_PROMPT = """你是一个知识图谱构建助手。请从以下文本中提取知识点和它们之间的关系。

要求：
1. 提取所有重要的知识点（概念、技术、方法等）
2. 识别知识点之间的前置依赖关系（PREREQUISITE_OF）和关联关系（RELATED_TO）
3. 每个知识点需要名称(name)和简短描述(description)
4. 关系类型只有两种：PREREQUISITE_OF（前置知识）和 RELATED_TO（相关知识）

请严格按以下 JSON 格式输出，不要输出其他内容：
```json
{{
  "nodes": [
    {{"name": "知识点名称", "description": "简短描述"}}
  ],
  "edges": [
    {{"source": "前置知识点", "target": "后续知识点", "relation": "PREREQUISITE_OF"}},
    {{"source": "知识点A", "target": "知识点B", "relation": "RELATED_TO"}}
  ]
}}
```

文本内容：
{content}"""


def _parse_llm_output(raw: str) -> dict[str, Any]:
    """解析 LLM 输出的 JSON，容错处理"""
    # 尝试从 markdown 代码块中提取 JSON
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        raw = raw[start:end].strip()
    elif "```" in raw:
        start = raw.index("```") + 3
        end = raw.index("```", start)
        raw = raw[start:end].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM output as JSON: %s", raw[:200])
        return {"nodes": [], "edges": []}


def extract_knowledge_from_text(content: str) -> dict[str, Any]:
    """从文本中提取知识点和关系（同步）

    Returns:
        {"nodes": [...], "edges": [...]}
    """
    llm = get_llm()
    prompt = ChatPromptTemplate.from_template(_EXTRACT_PROMPT)
    chain = prompt | llm | StrOutputParser()

    try:
        raw = chain.invoke({"content": content[:3000]})
        return _parse_llm_output(raw)
    except Exception as e:
        logger.warning("Knowledge extraction failed: %s", e)
        return {"nodes": [], "edges": []}


async def aextract_knowledge_from_text(content: str) -> dict[str, Any]:
    """从文本中提取知识点和关系（异步）"""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_template(_EXTRACT_PROMPT)
    chain = prompt | llm | StrOutputParser()

    try:
        raw = await chain.ainvoke({"content": content[:3000]})
        return _parse_llm_output(raw)
    except Exception as e:
        logger.warning("Knowledge extraction failed: %s", e)
        return {"nodes": [], "edges": []}


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

    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        # 拼接 batch 内的 chunk 内容
        combined = "\n\n---\n\n".join(doc.page_content for doc in batch)

        result = extract_knowledge_from_text(combined)

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
