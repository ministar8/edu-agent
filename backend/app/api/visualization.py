from fastapi import APIRouter

from app.models.schemas import KGImportRequest

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
                "tools": ["search_knowledge_base"],
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
async def get_rag_process_demo(query: str, collection: str = "general"):
    """RAG检索过程可视化数据"""
    from app.rag.retriever import rewrite_query, retrieve_with_scores

    original_query = query
    rewritten_query = rewrite_query(query)
    results = retrieve_with_scores(rewritten_query, collection_name=collection, k=5)

    steps = [
        {
            "step": 1,
            "name": "原始查询",
            "data": original_query,
            "type": "input",
        },
        {
            "step": 2,
            "name": "查询改写",
            "data": rewritten_query,
            "type": "transform",
        },
        {
            "step": 3,
            "name": "向量检索",
            "data": f"在 {collection} 集合中检索 Top-5 相似文档",
            "type": "search",
        },
        {
            "step": 4,
            "name": "检索结果",
            "data": results[:5],
            "type": "results",
        },
    ]

    return {"steps": steps, "total_chunks": len(results)}


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
async def get_knowledge_graph(category: str = None):
    """获取知识图谱可视化数据（节点+边）"""
    from app.rag.knowledge_graph import kg_manager
    return kg_manager.get_graph_data(category=category)


@router.post("/knowledge-graph/import")
async def import_knowledge_graph(request: KGImportRequest):
    """批量导入知识点和关系到知识图谱"""
    from app.rag.knowledge_graph import kg_manager
    nodes_data = [n.model_dump() for n in request.nodes]
    edges_data = [e.model_dump() for e in request.edges]
    kg_manager.import_from_data(nodes_data, edges_data)
    return {"success": True, "nodes": len(request.nodes), "edges": len(request.edges)}


DEMO_NODES = [
    {"name": "Python基础", "category": "programming", "description": "Python语法基础"},
    {"name": "数据类型", "category": "programming", "description": "数字、字符串、列表、字典等"},
    {"name": "控制流", "category": "programming", "description": "条件判断与循环"},
    {"name": "函数", "category": "programming", "description": "函数定义与调用"},
    {"name": "面向对象", "category": "programming", "description": "类与对象、继承、多态"},
    {"name": "装饰器", "category": "programming", "description": "函数装饰器与类装饰器"},
    {"name": "生成器", "category": "programming", "description": "yield与迭代器"},
    {"name": "机器学习基础", "category": "ml", "description": "ML基本概念与流程"},
    {"name": "数据预处理", "category": "ml", "description": "数据清洗与特征工程"},
    {"name": "线性回归", "category": "ml", "description": "回归分析基础"},
    {"name": "神经网络", "category": "dl", "description": "前馈网络与反向传播"},
    {"name": "深度学习", "category": "dl", "description": "CNN/RNN/Transformer"},
]

DEMO_EDGES = [
    {"source": "Python基础", "target": "数据类型", "relation": "PREREQUISITE_OF"},
    {"source": "数据类型", "target": "控制流", "relation": "PREREQUISITE_OF"},
    {"source": "控制流", "target": "函数", "relation": "PREREQUISITE_OF"},
    {"source": "函数", "target": "面向对象", "relation": "PREREQUISITE_OF"},
    {"source": "函数", "target": "装饰器", "relation": "PREREQUISITE_OF"},
    {"source": "面向对象", "target": "生成器", "relation": "PREREQUISITE_OF"},
    {"source": "Python基础", "target": "机器学习基础", "relation": "PREREQUISITE_OF"},
    {"source": "机器学习基础", "target": "数据预处理", "relation": "PREREQUISITE_OF"},
    {"source": "数据预处理", "target": "线性回归", "relation": "PREREQUISITE_OF"},
    {"source": "线性回归", "target": "神经网络", "relation": "PREREQUISITE_OF"},
    {"source": "神经网络", "target": "深度学习", "relation": "PREREQUISITE_OF"},
    {"source": "装饰器", "target": "生成器", "relation": "RELATED_TO"},
    {"source": "面向对象", "target": "装饰器", "relation": "RELATED_TO"},
]


@router.post("/knowledge-graph/seed")
async def seed_knowledge_graph():
    """一键导入示例知识图谱数据"""
    from app.rag.knowledge_graph import kg_manager
    kg_manager.import_from_data(DEMO_NODES, DEMO_EDGES)
    return {"success": True, "nodes": len(DEMO_NODES), "edges": len(DEMO_EDGES)}
