import logging
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.rag.vectorstore import vector_store_manager

logger = logging.getLogger(__name__)

# 相似度阈值：低于此分数的结果视为不相关，过滤掉
SCORE_THRESHOLD = 0.4

# 查询缓存：相同查询直接返回，避免重复 Embedding + 检索
_query_cache: dict[str, list[tuple[Document, float]]] = {}
_MAX_CACHE_SIZE = 200


def get_llm():
    """获取LLM实例（单例缓存）"""
    from langchain_openai import ChatOpenAI

    if not hasattr(get_llm, "_instance"):
        get_llm._instance = ChatOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE,
            model=settings.LLM_MODEL,
            temperature=0.3,
        )
    return get_llm._instance


@lru_cache(maxsize=128)
def rewrite_query(query: str) -> str:
    """查询改写，优化检索效果（带缓存，相同查询不重复调用LLM）"""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_template(
        "你是一个查询优化助手。请将以下学生问题改写为更适合检索的形式，"
        "提取关键知识点，去除口语化表达。\n\n"
        "原始问题: {query}\n\n改写后的检索查询:"
    )
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"query": query})


def _raw_search(query: str, collection_name: str, k: int) -> list[tuple[Document, float]]:
    """底层向量检索（带缓存）"""
    cache_key = f"{collection_name}:{query}"
    if cache_key in _query_cache:
        logger.debug("Cache hit for query: %s", query)
        return _query_cache[cache_key]

    store = vector_store_manager.get_store(collection_name)
    results = store.similarity_search_with_score(query, k=k)

    # 简单 LRU：超出上限时清空
    if len(_query_cache) > _MAX_CACHE_SIZE:
        _query_cache.clear()
    _query_cache[cache_key] = results

    return results


def retrieve_documents(
    query: str,
    collection_name: str = "knowledge",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rewrite: bool = False,
) -> list[Document]:
    """检索相关文档，过滤低相关度结果

    Args:
        use_rewrite: 是否启用查询改写（默认关闭以加速检索，
                     结果不足时可开启改写提升召回率）
    """
    search_query = rewrite_query(query) if use_rewrite else query
    results = _raw_search(search_query, collection_name, k)
    filtered = [doc for doc, score in results if score >= score_threshold]

    # 无结果时自动尝试查询改写
    if not filtered and not use_rewrite:
        logger.info("No results for '%s', trying with rewrite", query)
        search_query = rewrite_query(query)
        results = _raw_search(search_query, collection_name, k)
        filtered = [doc for doc, score in results if score >= score_threshold]

    return filtered


def retrieve_with_scores(
    query: str,
    collection_name: str = "knowledge",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rewrite: bool = False,
) -> list[dict]:
    """检索相关文档并返回相似度分数，过滤低相关度结果"""
    search_query = rewrite_query(query) if use_rewrite else query
    results = _raw_search(search_query, collection_name, k)
    filtered = [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": float(score),
        }
        for doc, score in results
        if score >= score_threshold
    ]

    # 无结果时自动尝试查询改写
    if not filtered and not use_rewrite:
        logger.info("No results for '%s', trying with rewrite", query)
        search_query = rewrite_query(query)
        results = _raw_search(search_query, collection_name, k)
        filtered = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score),
            }
            for doc, score in results
            if score >= score_threshold
        ]

    return filtered


def build_rag_context(docs: list[Document]) -> str:
    """将检索结果构建为上下文"""
    context_parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source_file", "未知来源")
        context_parts.append(f"[来源{i}: {source}]\n{doc.page_content}")
    return "\n\n".join(context_parts)
