from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import HTTPException, status

from app.schemas import KGImportRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/agent-graph")
async def get_agent_graph():
    """获取Agent协作流程图结构（供前端React Flow渲染）"""
    nodes = [
        {
            "id": "supervisor",
            "type": "supervisor",
            "position": {"x": 400, "y": 50},
            "data": {
                "label": "Supervisor 调度Agent",
                "description": "分析学生问题，路由到对应子Agent",
                "status": "idle",
            },
        },
        {
            "id": "knowledge_agent",
            "type": "agent",
            "position": {"x": 100, "y": 250},
            "data": {
                "label": "知识点检索Agent",
                "description": "RAG检索教材，生成带引用的讲解",
                "tools": ["knowledge_search", "text_search", "kg_search"],
                "status": "idle",
            },
        },
        {
            "id": "question_agent",
            "type": "agent",
            "position": {"x": 300, "y": 250},
            "data": {
                "label": "题目生成Agent",
                "description": "检索题库模板，生成新练习题",
                "tools": ["search_question_templates"],
                "status": "idle",
            },
        },
        {
            "id": "grading_agent",
            "type": "agent",
            "position": {"x": 500, "y": 250},
            "data": {
                "label": "批改评估Agent",
                "description": "检索标准答案，对比评分",
                "tools": ["search_standard_answer"],
                "status": "idle",
            },
        },
        {
            "id": "path_agent",
            "type": "agent",
            "position": {"x": 700, "y": 250},
            "data": {
                "label": "学习路径推荐Agent",
                "description": "检索知识图谱，推荐学习路径",
                "tools": ["query_knowledge_graph", "search_learning_path"],
                "status": "idle",
            },
        },
    ]

    edges = [
        {
            "id": "e-supervisor-knowledge",
            "source": "supervisor",
            "target": "knowledge_agent",
            "label": "知识点查询",
            "animated": True,
        },
        {
            "id": "e-supervisor-question",
            "source": "supervisor",
            "target": "question_agent",
            "label": "出题请求",
            "animated": True,
        },
        {
            "id": "e-supervisor-grading",
            "source": "supervisor",
            "target": "grading_agent",
            "label": "批改请求",
            "animated": True,
        },
        {
            "id": "e-supervisor-path",
            "source": "supervisor",
            "target": "path_agent",
            "label": "学习建议",
            "animated": True,
        },
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/rag-process")
async def get_rag_process_demo(query: str, collection: str = "data_structure"):
    """RAG检索过程可视化数据（统一检索管线）"""
    from app.rag.fusion import fuse_documents
    from app.rag.context import kg_context_supplement as _kg_context_supplement
    from app.rag.trace import retrieve_documents_with_trace

    try:
        docs, trace = retrieve_documents_with_trace(query=query, collection_name=collection, k=5, use_rerank=True)

        # 用 fuse_documents 生成最终上下文（复用 trace 的 docs，避免重复检索）
        kg_supplement = ""
        try:
            kg_supplement = _kg_context_supplement(query)
        except Exception as e:
            logger.debug("KG supplement skipped for visualization: %s", e)
        retrieval_depth = trace.get("policy", {}).get("retrieval_depth", "standard")
        fused = fuse_documents(docs, query="", kg_supplement=kg_supplement, depth=retrieval_depth)
        result_text = fused.final_context
        route_summary = trace.get("route_summary", {})
        kg_trace = trace.get("kg", {})
        hyde_trace = trace.get("hyde", {})
        counts = trace.get("counts", {})

        # 提取源文档节点
        source_nodes = []
        for doc in docs[:5]:
            source_nodes.append({
                "content": doc.page_content[:200] if doc.page_content else "",
                "score": float(doc.metadata.get("rerank_score", 0.0)),
                "metadata": doc.metadata,
            })

        steps = [
            {
                "step": 1,
                "name": "原始查询",
                "data": query,
                "type": "input",
            },
            {
                "step": 2,
                "name": "多路召回+BM25+KG扩展",
                "data": (
                    f"实际搜索集合: {', '.join(trace['collections'])}\n"
                    f"粗召回K: {trace['policy']['coarse_k']}；阈值: {trace['policy']['threshold']:.2f}\n"
                    f"路由数: {len(trace['routes'])}；原始合并结果: {counts.get('raw', 0)} 条\n"
                    f"各路命中: {route_summary.get('hits_by_route', {})}"
                ),
                "type": "search",
            },
            {
                "step": 3,
                "name": "Reranker重排+层级展开",
                "data": source_nodes[:5],
                "type": "results",
            },
            {
                "step": 4,
                "name": "上下文构建",
                "data": (
                    f"阶段统计: 去重后 {counts.get('after_dedup', 0)} 条 → "
                    f"阈值过滤后 {counts.get('after_threshold', 0)} 条 → "
                    f"重排后 {counts.get('after_rerank', 0)} 条 → "
                    f"HyDE后 {counts.get('after_hyde', counts.get('after_rerank', 0))} 条 → "
                    f"层级展开后 {counts.get('after_window', counts.get('after_expand', 0))} 条 → "
                    f"最终上下文 {counts.get('final', 0)} 条\n"
                    f"HyDE: triggered={hyde_trace.get('triggered', False)}, added={hyde_trace.get('added_count', 0)}\n"
                    f"KG: used={kg_trace.get('used', False)}, nodes={kg_trace.get('nodes_count', 0)}, "
                    f"edges={kg_trace.get('edges_count', 0)}, paths={kg_trace.get('paths_count', 0)}\n\n"
                    f"{result_text[:500] if result_text else '未构建上下文：当前集合中没有检索到相关内容，请确认知识库已入库，或切换到匹配的408科目集合。'}"
                ),
                "type": "output",
            },
        ]

        return {"steps": steps, "total_chunks": len(source_nodes), "trace": trace}
    except Exception as e:
        logger.error("RAG process visualization failed: %s", e, exc_info=True)
        return {
            "steps": [
                {"step": 1, "name": "原始查询", "data": query, "type": "input"},
                {"step": 2, "name": "错误", "data": str(e), "type": "error"},
            ],
            "total_chunks": 0,
        }


@router.get("/agent-status")
async def get_agent_status():
    """获取所有Agent当前状态"""
    agents = [
        {
            "id": "supervisor",
            "name": "Supervisor 调度Agent",
            "status": "idle",
            "description": "分析问题并路由分发",
        },
        {
            "id": "knowledge_agent",
            "name": "知识点检索Agent",
            "status": "idle",
            "description": "RAG检索教材知识",
        },
        {
            "id": "question_agent",
            "name": "题目生成Agent",
            "status": "idle",
            "description": "生成练习题",
        },
        {
            "id": "grading_agent",
            "name": "批改评估Agent",
            "status": "idle",
            "description": "批改学生答案",
        },
        {
            "id": "path_agent",
            "name": "学习路径推荐Agent",
            "status": "idle",
            "description": "推荐学习路径",
        },
    ]
    return {"agents": agents}


@router.get("/knowledge-graph")
async def get_knowledge_graph(category: str | None = None):
    """获取知识图谱可视化数据（节点+边）"""
    try:
        from app.rag.knowledge_graph import get_kg_manager
        return get_kg_manager().get_graph_data(category=category)
    except Exception as e:
        logger.error("Knowledge graph fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"知识图谱查询失败: {e}")


@router.post("/knowledge-graph/import")
async def import_knowledge_graph(request: KGImportRequest):
    """批量导入知识点和关系到知识图谱"""
    try:
        from app.rag.knowledge_graph import get_kg_manager
        nodes_data = [n.model_dump() for n in request.nodes]
        edges_data = [e.model_dump() for e in request.edges]
        get_kg_manager().import_from_data(nodes_data, edges_data)
        return {"success": True, "nodes": len(request.nodes), "edges": len(request.edges)}
    except Exception as e:
        logger.error("Knowledge graph import failed: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"知识图谱导入失败: {e}")


DEMO_NODES = [
    {"name": "数据结构", "category": "data_structure", "description": "数据结构基础概念"},
    {"name": "线性表", "category": "data_structure", "description": "顺序表与链表"},
    {"name": "树与二叉树", "category": "data_structure", "description": "二叉树遍历、BST、AVL、红黑树"},
    {"name": "图", "category": "data_structure", "description": "图的存储、遍历、最短路径、最小生成树"},
    {"name": "查找", "category": "data_structure", "description": "顺序查找、折半查找、B树、散列表"},
    {"name": "排序", "category": "data_structure", "description": "插入/交换/选择/归并/基数排序"},
    {"name": "数据的表示和运算", "category": "computer_organization", "description": "定点数、浮点数、ALU"},
    {"name": "存储系统", "category": "computer_organization", "description": "主存、Cache、虚拟存储器"},
    {"name": "指令系统", "category": "computer_organization", "description": "指令格式、寻址方式、CISC/RISC"},
    {"name": "CPU", "category": "computer_organization", "description": "数据通路、控制器、流水线"},
    {"name": "进程管理", "category": "operating_system", "description": "进程与线程、调度、同步与互斥、死锁"},
    {"name": "内存管理", "category": "operating_system", "description": "分区、分页、分段、虚拟内存"},
    {"name": "数据链路层", "category": "computer_network", "description": "差错控制、流量控制、CSMA/CD"},
    {"name": "网络层", "category": "computer_network", "description": "IP协议、路由算法、NAT"},
    {"name": "传输层", "category": "computer_network", "description": "TCP/UDP、拥塞控制"},
    {"name": "应用层", "category": "computer_network", "description": "DNS、HTTP、FTP、电子邮件"},
]

DEMO_EDGES = [
    {"source": "数据结构", "target": "线性表", "relation": "PREREQUISITE_OF"},
    {"source": "线性表", "target": "树与二叉树", "relation": "PREREQUISITE_OF"},
    {"source": "树与二叉树", "target": "图", "relation": "PREREQUISITE_OF"},
    {"source": "图", "target": "查找", "relation": "PREREQUISITE_OF"},
    {"source": "查找", "target": "排序", "relation": "PREREQUISITE_OF"},
    {"source": "数据的表示和运算", "target": "存储系统", "relation": "PREREQUISITE_OF"},
    {"source": "存储系统", "target": "指令系统", "relation": "PREREQUISITE_OF"},
    {"source": "指令系统", "target": "CPU", "relation": "PREREQUISITE_OF"},
    {"source": "数据链路层", "target": "网络层", "relation": "PREREQUISITE_OF"},
    {"source": "网络层", "target": "传输层", "relation": "PREREQUISITE_OF"},
    {"source": "传输层", "target": "应用层", "relation": "PREREQUISITE_OF"},
    {"source": "排序", "target": "进程管理", "relation": "RELATED_TO"},
    {"source": "CPU", "target": "进程管理", "relation": "RELATED_TO"},
    {"source": "进程管理", "target": "内存管理", "relation": "PREREQUISITE_OF"},
    {"source": "内存管理", "target": "存储系统", "relation": "RELATED_TO"},
]


@router.post("/knowledge-graph/seed")
async def seed_knowledge_graph():
    """一键导入示例知识图谱数据"""
    try:
        from app.rag.knowledge_graph import get_kg_manager
        get_kg_manager().import_from_data(DEMO_NODES, DEMO_EDGES)
        return {"success": True, "nodes": len(DEMO_NODES), "edges": len(DEMO_EDGES)}
    except Exception as e:
        logger.error("Knowledge graph seed failed: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"示例数据导入失败: {e}")