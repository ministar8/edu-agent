"""RAG 共享工具函数

消除各模块间的重复代码：token 估算、查询归一化、关键词提取、内容类型检测。
统一维护点，所有模块从此导入。
"""

from __future__ import annotations

import logging
import re

import jieba

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────

_MAX_QUERY_TERMS = 6

_QUERY_STOP_WORDS = frozenset({
    "什么", "怎么", "如何", "为什么", "请问", "一下", "一下子", "有关", "关于", "这个", "那个",
    "哪些", "是否", "可以", "一下吧", "帮我", "讲解", "解释", "说明", "作用", "使用", "方法",
    "是", "的", "了", "在", "有", "和", "与", "及", "或", "等", "都", "也", "还", "又",
    "那", "这", "被", "把", "从", "到", "对", "向", "给", "让", "用", "以",
})

_BM25_STOP_WORDS = _QUERY_STOP_WORDS  # BM25 shares the same stop words as query extraction


# ── Token 估算 ───────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """粗估 token 数：中文 1 字符 ≈ 1.5 tokens，ASCII 1 字符 ≈ 0.25 tokens"""
    cn = sum(1 for c in text if '一' <= c <= '鿿')
    en = len(text) - cn
    return int(cn * 1.5 + en * 0.25)


# ── 查询归一化 ───────────────────────────────────────

def normalize_query_text(query: str) -> str:
    """统一查询归一化：去除多余空白"""
    return re.sub(r"\s+", " ", str(query).strip())


# ── 关键词提取 ───────────────────────────────────────

def extract_query_terms(query: str, max_terms: int = _MAX_QUERY_TERMS) -> list[str]:
    """用 jieba 精准分词提取查询关键词

    jieba.cut() 对中文精准分词，过滤停用词后保留有意义的术语词。
    英文 token 通过 regex 补充提取，避免 jieba 将英文缩写误切。
    """
    normalized = normalize_query_text(query)
    if not normalized:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    # jieba 精准分词
    for word in jieba.cut(normalized):
        word = word.strip()
        if not word or word in _QUERY_STOP_WORDS or word.lower() in _QUERY_STOP_WORDS:
            continue
        if len(word) == 1 and not word.isascii():
            continue
        lowered = word.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(word)
        if len(terms) >= max_terms:
            break

    # 补充：regex 提取英文缩写/术语
    en_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{1,}", normalized)
    for token in en_tokens:
        lowered = token.lower()
        if lowered not in seen and lowered not in _QUERY_STOP_WORDS:
            seen.add(lowered)
            terms.append(token)
            if len(terms) >= max_terms:
                break

    return terms


def get_bm25_stop_words() -> frozenset[str]:
    return _BM25_STOP_WORDS


# ── 内容类型检测 ─────────────────────────────────────

def detect_content_type(text: str, metadata: dict) -> str:
    """检测 chunk 内容类型

    供 enhancer.py 和 splitter.py 共用，避免跨模块循环依赖。
    """
    stripped = text.strip()
    if not stripped:
        return "empty"

    heading_title = str(metadata.get("heading_title") or "").lower()
    source_ext = str(metadata.get("source_ext") or "").lower()

    if metadata.get("chunk_role") == "merged_qa" or metadata.get("section.chunk_role") == "merged_qa":
        return "merged_qa"

    if "```" in stripped or "~~~" in stripped:
        return "code_mixed"
    if re.search(r"(^|\n)\s{4,}\S", text):
        return "code_mixed"
    if re.search(r"(^|\n)\|.+\|(\n|$)", stripped) and re.search(r"(^|\n)\|[-:| ]+\|(\n|$)", stripped):
        return "table"
    if re.search(r"\$\$.+?\$\$", stripped, re.DOTALL):
        return "formula"
    if re.search(r"(^|\n)#{1,4}\s+", text):
        return "section"
    if re.search(r"(^|\n)\s*[-*+]\s+", text) or re.search(r"(^|\n)\s*\d+[.)、]\s+", text):
        return "list"
    if source_ext == ".md" and "题" in heading_title:
        return "exercise"
    if source_ext == ".md" and any(token in heading_title for token in ["答案", "解析"]):
        return "answer"
    if re.search(r"def |class |import |from .* import |if __name__ == ['\"]__main__['\"]", text):
        return "code_mixed"
    return "text"


# ── LLM getter ───────────────────────────────────────

def _is_deepseek_api(api_base: str, model: str) -> bool:
    """判断当前 LLM 是否为 DeepSeek 系列（需传 enable_thinking 等专有参数）

    检测逻辑：
    1. API base 含 "deepseek" → DeepSeek 官方 API
    2. 模型名含 "deepseek" → 通过第三方代理（如 DashScope）调用的 DeepSeek 模型
    """
    return "deepseek" in (api_base or "").lower() or "deepseek" in (model or "").lower()


def get_llm(streaming: bool = True, temperature: float = 0.3):
    """获取 LLM 实例（单例缓存）

    从 retriever.py 迁移至此，消除各模块对 retriever.py 的耦合。

    Args:
        streaming: 是否启用流式输出（默认 True，用于 Agent 对话）
        temperature: 生成温度（0.0=确定性评估，0.3=创造性生成）
    """
    from langchain_openai import ChatOpenAI
    from app.config import settings

    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY must be set in .env or environment variables")

    cache_key = "|".join([
        settings.LLM_API_BASE,
        settings.LLM_MODEL,
        settings.LLM_API_KEY[-8:],
        "stream" if streaming else "no_stream",
        f"temperature={temperature}",
    ])

    if not hasattr(get_llm, "_instances"):
        get_llm._instances = {}

    if cache_key not in get_llm._instances:
        logger.info(
            "Creating LLM client: base=%s model=%s streaming=%s key_prefix=%s key_len=%d",
            settings.LLM_API_BASE,
            settings.LLM_MODEL,
            streaming,
            settings.LLM_API_KEY[:8],
            len(settings.LLM_API_KEY),
        )
        kwargs = dict(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE,
            model=settings.LLM_MODEL,
            temperature=temperature,
            streaming=streaming,
        )
        # enable_thinking 是 DeepSeek 专有参数，禁用思考模式以保证结构化输出稳定
        # 检测：API base 或 模型名 含 "deepseek" 均视为 DeepSeek 系列
        if _is_deepseek_api(settings.LLM_API_BASE, settings.LLM_MODEL):
            kwargs["extra_body"] = {"enable_thinking": False}
        get_llm._instances[cache_key] = ChatOpenAI(**kwargs)
    return get_llm._instances[cache_key]
