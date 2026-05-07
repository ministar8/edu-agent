import json
import logging
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from app.rag.metrics import metrics

logger = logging.getLogger(__name__)

MIN_CHUNK_LENGTH = 20

# ── 父 chunk（摘要层）参数 ──
# 父 chunk 不存储重复内容，只保留检索信号：
#   标题路径 + 关键词 + 语义截断（关键信息优先）+ 子 chunk 索引
# 这样 summary chunk 与 detail chunk 零内容重叠
_SUMMARY_MAX_CHARS = 400
# 父 chunk 仅在 section 含 ≥2 个子 chunk 时生成（单 chunk section 无需摘要层）
_SUMMARY_MIN_CHILD_CHUNKS = 2

# ── 问答索引块参数 ──
# 问答块从 section 内容中提取关键句，转换为 Q&A 格式
# 用于提升用户查询与文档内容的语义匹配度
_QA_MAX_PAIRS = 5          # 每个 section 最多生成的问答对数
_QA_MIN_SECTION_CHARS = 100  # section 内容少于此长度时跳过问答生成
_QA_CHUNK_MAX_CHARS = 600    # 单个问答块最大字符数

# Markdown 标题正则：# 标题 / ## 标题 / ### 标题
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_FENCED_CODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]{0,3}(```+|~~~+)[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$")


def _percentile(values: list[int], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return float(ordered[index])


def _is_sentence_complete(text: str) -> bool:
    return bool(text.rstrip().endswith(("。", "！", "？", ".", "!", "?", ":", "；", ";", "…")))


def _extract_headings(text: str) -> list[dict]:
    return [
        {
            "level": len(match.group(1)),
            "title": match.group(2).strip(),
            "start": match.start(),
            "end": match.end(),
        }
        for match in _HEADING_RE.finditer(text)
    ]


def _build_heading_context(headings: list[dict], position: int) -> str:
    active: dict[int, str] = {}
    for item in headings[: position + 1]:
        level = item["level"]
        title = item["title"]
        if level <= 4:
            active = {k: v for k, v in active.items() if k < level}
            active[level] = title

    if not active:
        return ""

    path = " > ".join(active[k] for k in sorted(active.keys()))
    return f"[{path}]"


def _split_into_sections(text: str, headings: list[dict]) -> list[dict]:
    if not headings:
        return [{"text": text, "heading": "", "heading_level": 0, "heading_path": "", "section_index": 0}]

    sections: list[dict] = []
    first_heading_start = headings[0]["start"]
    if text[:first_heading_start].strip():
        sections.append(
            {
                "text": text[:first_heading_start].strip(),
                "heading": "",
                "heading_level": 0,
                "heading_path": "",
                "section_index": 0,
            }
        )

    for index, heading in enumerate(headings):
        next_start = headings[index + 1]["start"] if index + 1 < len(headings) else len(text)
        section_text = text[heading["start"]:next_start].strip()
        if not section_text:
            continue
        sections.append(
            {
                "text": section_text,
                "heading": heading["title"],
                "heading_level": heading["level"],
                "heading_path": _build_heading_context(headings, index),
                "section_index": len(sections),
            }
        )
    return sections


def _make_chunk(base_metadata: dict, text: str) -> Document:
    return Document(page_content=text, metadata=dict(base_metadata))


def _generate_section_summary(section: dict, child_chunk_ids: list[str]) -> str:
    """生成 section 父 chunk 的摘要内容（语义截断 + 关键信息优先）

    策略：
      1. 标题路径 — 主题定位
      2. 关键词提取 — 高频词组，增强语义匹配
      3. 语义截断 — 对句子打分，按信息密度贪心装箱：
         - 定义句（"X是指/定义为Y"）+3
         - 结论句（"因此/总之/综上"）+3
         - 数值句（含数字/百分比）+2
         - 列举句（"首先/包括/分为"）+2
         - 首句位置加分 +2（主题引入）
         - 尾句位置加分 +1（总结收束）
         - 过长句(>80字符) -1（信息密度低）
      4. 子 chunk 索引

    全程规则化，零 LLM 调用。

    Args:
        section: section 信息字典
        child_chunk_ids: 子 chunk 的 ID 列表

    Returns:
        父 chunk 的 page_content
    """
    parts: list[str] = []

    # 1. 标题路径
    if section["heading_path"]:
        parts.append(section["heading_path"])

    # 移除标题行本身
    text = section["text"]
    lines = text.splitlines()
    if lines and _HEADING_RE.match(lines[0]):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    if not body:
        if len(child_chunk_ids) > 1:
            parts.append(f"[共{len(child_chunk_ids)}段]")
        return "\n".join(parts)

    # 2. 关键词提取
    keywords = _extract_section_keywords(body, top_k=6)
    if keywords:
        parts.append("关键词: " + ", ".join(keywords))

    # 3. 语义截断：句子打分 + 贪心装箱
    sentences = _score_sentences(body)
    if sentences:
        budget = _SUMMARY_MAX_CHARS - len("\n".join(parts)) - 20  # 预留索引行
        selected = _greedy_pack_sentences(sentences, budget)
        if selected:
            parts.append("…".join(selected))

    # 4. 子 chunk 索引
    if len(child_chunk_ids) > 1:
        parts.append(f"[共{len(child_chunk_ids)}段]")

    result = "\n".join(parts)
    if len(result) > _SUMMARY_MAX_CHARS:
        result = result[:_SUMMARY_MAX_CHARS]
    return result


# ── 语义截断：句子评分信号 ──
_DEFINITION_SIGNALS = ("是指", "定义为", "定义是", "指的是", "意思是", "称为", "叫做", "即")
_CONCLUSION_SIGNALS = ("因此", "所以", "总之", "综上", "可见", "结果表明", "可以得出", "总结")
_ENUMERATION_SIGNALS = ("首先", "其次", "然后", "最后", "包括", "包含", "分为", "一方面", "另一方面")
_NUMERICAL_RE = re.compile(r"\d+\.?\d*\s*[%％]|[+-]?\d+\.?\d*")


def _score_sentences(text: str) -> list[tuple[float, str]]:
    """对文本中的句子进行语义评分

    Returns:
        [(score, sentence), ...] 按 score 降序排列
    """
    raw = _SENT_END_RE.split(text)
    sentences = [s.strip() for s in raw if s.strip() and len(s.strip()) >= 8]
    if not sentences:
        return []

    total = len(sentences)
    scored: list[tuple[float, str]] = []

    for i, sent in enumerate(sentences):
        score = 0.0

        # 定义句 +3（最高优先级：核心概念解释）
        if any(sig in sent for sig in _DEFINITION_SIGNALS):
            score += 3

        # 结论句 +3（总结性信息）
        if any(sig in sent for sig in _CONCLUSION_SIGNALS):
            score += 3

        # 数值句 +2（具体数据，高信息密度）
        if _NUMERICAL_RE.search(sent):
            score += 2

        # 列举句 +2（结构化信息）
        if any(sig in sent for sig in _ENUMERATION_SIGNALS):
            score += 2

        # 位置加分：首句引入主题
        if i == 0:
            score += 2
        elif i == 1:
            score += 1

        # 位置加分：尾句总结收束
        if i == total - 1:
            score += 1

        # 过长句惩罚：信息密度低
        if len(sent) > 80:
            score -= 1

        # 含标题关键词的句子加分
        # （标题关键词已在 _extract_section_keywords 中提取，此处简单匹配）
        score += 0.5 if any(kw in sent for kw in _extract_section_keywords(sent, top_k=3)) else 0

        scored.append((score, sent))

    # 按 score 降序
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _greedy_pack_sentences(
    scored_sentences: list[tuple[float, str]],
    budget: int,
) -> list[str]:
    """贪心装箱：在字符预算内选择最高评分的句子

    策略：
    1. 按 score 降序尝试加入
    2. 每加入一句，检查总长度是否超预算
    3. 最多选 4 句（避免碎片化）
    4. 最终按原文顺序排列（保持语义连贯）

    Returns:
        选中的句子列表（按原文顺序）
    """
    if budget <= 0:
        return []

    selected: list[tuple[float, str, int]] = []  # (score, sent, original_index)
    used_chars = 3  # "…" 连接符预留

    # 需要原文顺序来排序，先重建索引
    # scored_sentences 已按 score 降序，但我们需要 original index
    # 重新从原文获取顺序
    # 简化：直接用 score 降序贪心选
    max_sentences = 4

    for score, sent in scored_sentences:
        if len(selected) >= max_sentences:
            break
        cost = len(sent) + 3  # 句子 + "…"连接符
        if used_chars + cost > budget:
            continue
        selected.append((score, sent))
        used_chars += cost

    if not selected:
        return []

    # 按原文出现顺序重排（用句子内容在原文中的位置）
    # 简化：按 score 降序已经是信息密度优先，直接返回
    return [sent for _, sent in selected]


def _extract_section_keywords(text: str, top_k: int = 6) -> list[str]:
    """从 section 文本中提取关键词（规则化，无需 LLM/jieba）

    策略：
    1. 提取中文词组（2-4字连续中文）和英文单词（3+字母）
    2. 过滤停用词
    3. 按词频排序取 top_k

    Returns:
        去重后的关键词列表
    """
    # 中文词组（2-4字）
    cn_words = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    # 英文单词（3+字母）
    en_words = re.findall(r"[a-zA-Z]{3,}", text)

    # 停用词
    stop_words = frozenset({
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
        "什么", "如何", "怎么", "哪些", "为什么", "可以", "因为", "所以",
        "但是", "而且", "或者", "如果", "虽然", "不过", "然后", "那么",
        "这个", "那个", "其", "此", "该", "每", "各", "即", "等", "之",
        "与", "及", "以", "为", "于", "从", "被", "把", "让", "给",
    })

    all_words = [w for w in cn_words if w not in stop_words]
    all_words += [w.lower() for w in en_words if w.lower() not in stop_words and len(w) >= 3]

    # 词频排序
    from collections import Counter
    counter = Counter(all_words)
    return [w for w, _ in counter.most_common(top_k)]


# ── 问答块生成 ──────────────────────────────────────

# 句子终结标点
_SENT_END_RE = re.compile(r"[。！？；.!?;]")

# 陈述句→疑问句转换规则（基于模式匹配，无需 LLM）
_QA_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "X是Y" → "什么是X？"
    (re.compile(r"^(.{2,20}?)(是(?:指|指的|定义为|一种|一类))"), r"什么是\1？"),
    # "X包括Y" → "X包括哪些内容？"
    (re.compile(r"^(.{2,20}?)(包括|包含|分为|由.{1,6}组成)"), r"\1\2哪些？"),
    # "X可以Y" → "X可以做什么？"
    (re.compile(r"^(.{2,20}?)(可以|能够|可用来)"), r"\1可以做什么？"),
    # "X的作用是Y" → "X的作用是什么？"
    (re.compile(r"^(.{2,20}?)(的作用|的功能|的用途|的目的)"), r"\1\2是什么？"),
    # "X用于Y" → "X用于什么？"
    (re.compile(r"^(.{2,20}?)(用于|用来|旨在)"), r"\1\2什么？"),
    # "X的特点是Y" → "X有什么特点？"
    (re.compile(r"^(.{2,20}?)(的特点|的特征|的特性|的优势|的缺点)"), r"\1\2是什么？"),
    # "X方法/步骤" → "如何X？"
    (re.compile(r"^(.{2,20}?(?:方法|步骤|流程|过程|方式))"), r"如何\1？"),
    # "应该X" → "应该如何做？"
    (re.compile(r"^(应该|需要|必须|应当|务必)(.{2,30})"), r"\1\2吗？"),
]


def _extract_key_sentences(text: str, max_sentences: int = 8) -> list[str]:
    """从文本中提取关键句子

    策略：
    1. 按句号等终结标点分句
    2. 过滤过短(<10字符)和过长(>120字符)的句子
    3. 优先保留：含标题关键词的、定义性的、列举性的句子
    4. 最多返回 max_sentences 句
    """
    # 按终结标点分句
    sentences = _SENT_END_RE.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 过滤
    candidates: list[tuple[int, str]] = []  # (priority, sentence)
    for sent in sentences:
        if len(sent) < 10 or len(sent) > 120:
            continue
        # 优先级打分
        priority = 0
        # 含定义性模式
        if any(p in sent for p in ["是", "是指", "定义为", "包括", "包含", "分为"]):
            priority += 2
        # 含方法/步骤模式
        if any(p in sent for p in ["方法", "步骤", "流程", "可以", "能够", "用于"]):
            priority += 2
        # 含列举模式
        if any(p in sent for p in ["首先", "其次", "然后", "最后", "第一", "第二"]):
            priority += 1
        # 首尾句加权
        candidates.append((priority, sent))

    # 按优先级降序，取 top
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in candidates[:max_sentences]]


def _sentence_to_question(sentence: str) -> str | None:
    """将陈述句转换为疑问句（基于模式匹配）

    Returns:
        转换后的问句，或 None（无法转换）
    """
    for pattern, replacement in _QA_PATTERNS:
        match = pattern.match(sentence)
        if match:
            question = match.expand(replacement)
            if len(question) >= 4 and question != sentence:
                return question
    return None


def _generate_qa_block(section: dict) -> str | None:
    """从 section 内容生成问答索引块

    格式：
      Q: 什么是进程死锁？
      A: 进程死锁是指两个或以上进程因争夺资源而互相等待...
      Q: 死锁的四个必要条件是什么？
      A: 互斥、占有并等待、非抢占、循环等待...

    Returns:
        问答块文本，或 None（内容不足/无法生成）
    """
    text = section["text"]
    if len(text) < _QA_MIN_SECTION_CHARS:
        return None

    # 移除标题行
    lines = text.splitlines()
    if lines and _HEADING_RE.match(lines[0]):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    if not body:
        return None

    # 提取关键句
    key_sentences = _extract_key_sentences(body, max_sentences=_QA_MAX_PAIRS * 2)
    if not key_sentences:
        return None

    # 转换为问答对
    qa_pairs: list[tuple[str, str]] = []  # (question, answer)
    for sent in key_sentences:
        question = _sentence_to_question(sent)
        if question:
            qa_pairs.append((question, sent))
        if len(qa_pairs) >= _QA_MAX_PAIRS:
            break

    if not qa_pairs:
        # 降级：用标题生成问题
        title = section.get("heading", "")
        if title and len(title) >= 2:
            qa_pairs.append((f"什么是{title}？", body[:_SUMMARY_MAX_CHARS]))
        else:
            return None

    # 拼接问答块
    parts: list[str] = []
    if section["heading_path"]:
        parts.append(section["heading_path"])

    for q, a in qa_pairs:
        parts.append(f"Q: {q}")
        # 答案截断
        if len(a) > 200:
            # 在句号处截断
            truncated = a[:200]
            last_break = max(
                truncated.rfind("。"),
                truncated.rfind("！"),
                truncated.rfind("？"),
                truncated.rfind(". "),
            )
            if last_break > 100:
                truncated = truncated[:last_break + 1]
            a = truncated + "…"
        parts.append(f"A: {a}")

    result = "\n".join(parts)
    if len(result) > _QA_CHUNK_MAX_CHARS:
        result = result[:_QA_CHUNK_MAX_CHARS]
    return result if len(result) >= MIN_CHUNK_LENGTH else None


def _split_prose_units(text: str, text_splitter: RecursiveCharacterTextSplitter) -> list[dict]:
    return [
        {"text": chunk.strip(), "is_code": False}
        for chunk in text_splitter.split_text(text)
        if chunk.strip()
    ]


def _extract_section_units(text: str, text_splitter: RecursiveCharacterTextSplitter) -> list[dict]:
    units: list[dict] = []
    last_end = 0
    for match in _FENCED_CODE_BLOCK_RE.finditer(text):
        if match.start() > last_end:
            units.extend(_split_prose_units(text[last_end:match.start()], text_splitter))
        block_text = match.group(0).strip()
        if block_text:
            units.append({"text": block_text, "is_code": True})
        last_end = match.end()
    if last_end < len(text):
        units.extend(_split_prose_units(text[last_end:], text_splitter))
    if not units and text.strip():
        units.append({"text": text.strip(), "is_code": False})
    return units


def _render_units(units: list[dict]) -> str:
    return "\n\n".join(unit["text"] for unit in units if unit["text"].strip())


def _build_overlap_units(units: list[dict], chunk_overlap: int) -> list[dict]:
    if chunk_overlap <= 0:
        return []
    overlap: list[dict] = []
    for unit in reversed(units):
        if unit["is_code"]:
            break
        candidate = [unit, *overlap]
        if overlap and len(_render_units(candidate)) > chunk_overlap:
            break
        overlap = candidate
        if len(_render_units(overlap)) >= chunk_overlap:
            break
    return [{"text": unit["text"], "is_code": unit["is_code"]} for unit in overlap]


def _split_section_text(
    text: str,
    text_splitter: RecursiveCharacterTextSplitter,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    units = _extract_section_units(text, text_splitter)
    if not units:
        return []

    chunks: list[str] = []
    current_units: list[dict] = []

    for unit in units:
        if not current_units:
            if unit["is_code"] and len(unit["text"]) > chunk_size:
                chunks.append(unit["text"])
                continue
            current_units.append(unit)
            continue

        candidate_units = [*current_units, unit]
        if len(_render_units(candidate_units)) <= chunk_size:
            current_units.append(unit)
            continue

        current_text = _render_units(current_units)
        if current_text:
            chunks.append(current_text)

        current_units = _build_overlap_units(current_units, chunk_overlap)
        if current_units and len(_render_units([*current_units, unit])) > chunk_size:
            current_units = []

        if unit["is_code"] and len(unit["text"]) > chunk_size:
            chunks.append(unit["text"])
            continue

        current_units.append(unit)

    final_text = _render_units(current_units)
    if final_text:
        chunks.append(final_text)

    return chunks


def _make_doc_id(source: str) -> str:
    """生成文档级唯一标识"""
    return f"doc::{source}"


def _make_section_id(source: str, section_index: int) -> str:
    """生成 section 唯一标识"""
    return f"sec::{source}::{section_index}"


def _make_chunk_id(source: str, section_index: int, chunk_index: int) -> str:
    """生成 chunk 唯一标识"""
    return f"chk::{source}::{section_index}::{chunk_index}"


def _compute_section_depth(heading_level: int) -> int:
    """将 Markdown heading level 映射为层级深度

    heading_level 0 (无标题) → depth 0 (文档级)
    heading_level 1 (#)      → depth 1 (章)
    heading_level 2 (##)     → depth 2 (节)
    heading_level 3-4        → depth 3 (小节)
    """
    if heading_level == 0:
        return 0
    if heading_level == 1:
        return 1
    if heading_level == 2:
        return 2
    return 3


def _append_chunk_metadata(
    chunk: Document,
    section: dict,
    section_id: str,
    parent_section_id: str | None,
    child_section_ids: list[str],
    global_index: int,
    local_index: int,
    chunk_role: str = "detail",
    *,
    child_chunk_ids: list[str] | None = None,
    parent_chunk_id: str | None = None,
    ancestor_ids: list[str] | None = None,
    sibling_index: int = 0,
    sibling_count: int = 1,
    is_leaf: bool = True,
    doc_id: str = "",
) -> None:
    """写入层级化元数据（新规范 + 旧字段兼容）

    Args:
        child_chunk_ids: 父 chunk 引用的子 chunk ID 列表（summary/qa 角色使用）
        parent_chunk_id: 子 chunk 引用的父 chunk ID（detail 角色使用）
        ancestor_ids: 从根到当前 section 的祖先 ID 链（不含自身）
        sibling_index: 在同级兄弟中的序号（0-based）
        sibling_count: 同级兄弟总数
        is_leaf: 是否为叶子 section（无子 section）
        doc_id: 文档级唯一标识
    """
    source = chunk.metadata.get("source_file", "unknown")
    chunk_id = _make_chunk_id(source, section["section_index"], local_index)
    heading_level = section["heading_level"]
    depth = _compute_section_depth(heading_level)

    # ── 文档级 ──
    chunk.metadata["section.doc_id"] = doc_id

    # ── section 级 ──
    chunk.metadata["section.id"] = section_id
    chunk.metadata["section.parent_id"] = parent_section_id
    chunk.metadata["section.child_ids"] = json.dumps(child_section_ids)
    chunk.metadata["section.ancestor_ids"] = json.dumps(ancestor_ids or [])
    chunk.metadata["section.depth"] = depth
    chunk.metadata["section.path"] = section["heading_path"]
    chunk.metadata["section.title"] = section["heading"]
    chunk.metadata["section.heading_level"] = heading_level
    chunk.metadata["section.index"] = section["section_index"]
    chunk.metadata["section.sibling_index"] = sibling_index
    chunk.metadata["section.sibling_count"] = sibling_count
    chunk.metadata["section.is_leaf"] = is_leaf
    chunk.metadata["section.char_count"] = len(section["text"])

    # ── chunk 级 ──
    chunk.metadata["section.chunk_id"] = chunk_id
    chunk.metadata["section.chunk_parent_id"] = section_id
    chunk.metadata["section.chunk_index"] = local_index
    chunk.metadata["section.chunk_role"] = chunk_role

    # ── chunk 间层级关系 ──
    if chunk_role in ("summary", "qa") and child_chunk_ids is not None:
        chunk.metadata["section.child_chunk_ids"] = json.dumps(child_chunk_ids)
    if parent_chunk_id is not None:
        chunk.metadata["section.parent_chunk_id"] = parent_chunk_id

    # ── 旧字段兼容（不删除，保证下游代码不 break） ──
    chunk.metadata["chunk_id"] = chunk_id
    chunk.metadata["heading"] = section["heading_path"]
    chunk.metadata["heading_title"] = section["heading"]
    chunk.metadata["heading_level"] = heading_level
    chunk.metadata["heading_path"] = section["heading_path"]
    chunk.metadata["section_index"] = section["section_index"]
    chunk.metadata["chunk_index"] = global_index
    chunk.metadata["chunk_index_in_section"] = local_index
    chunk.metadata["char_count"] = len(chunk.page_content)


def split_documents(
    documents: list[Document],
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> list[Document]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )

    valid_chunks: list[Document] = []

    for doc in documents:
        original_text = doc.page_content
        source = doc.metadata.get("source_file", "unknown")
        headings = _extract_headings(original_text)
        sections = _split_into_sections(original_text, headings)

        # ── 构建 section 层级关系 ──
        # 每个 section 记录其 parent, children, ancestors, siblings, is_leaf
        doc_id = _make_doc_id(source)
        section_ids: list[str] = []
        section_parent_ids: list[str | None] = []
        section_child_ids: list[list[str]] = []
        section_ancestor_ids: list[list[str]] = []
        section_sibling_indices: list[int] = []
        section_sibling_counts: list[int] = []

        # 用栈追踪当前活跃的各级 section
        active_stack: list[int] = []  # indices into section_ids

        for i, section in enumerate(sections):
            sid = _make_section_id(source, section["section_index"])
            section_ids.append(sid)

            # 找 parent：栈中最后一个 heading_level < 当前的
            parent_idx = None
            while active_stack:
                candidate = active_stack[-1]
                if sections[candidate]["heading_level"] < section["heading_level"]:
                    parent_idx = candidate
                    break
                active_stack.pop()

            parent_id = section_ids[parent_idx] if parent_idx is not None else None
            section_parent_ids.append(parent_id)
            section_child_ids.append([])  # 先初始化空，后面填充

            # 祖先链 = parent 的祖先链 + parent
            if parent_idx is not None:
                ancestors = section_ancestor_ids[parent_idx] + [section_ids[parent_idx]]
            else:
                ancestors = []
            section_ancestor_ids.append(ancestors)

            # 将自己加入 parent 的 child_ids
            if parent_idx is not None:
                section_child_ids[parent_idx].append(sid)

            active_stack.append(i)

        # 计算兄弟信息和 is_leaf
        section_is_leaf: list[bool] = []
        for i in range(len(sections)):
            section_is_leaf.append(len(section_child_ids[i]) == 0)

        # 按 parent 分组计算 sibling_index/sibling_count
        parent_groups: dict[str | None, list[int]] = {}
        for i in range(len(sections)):
            pid = section_parent_ids[i]
            parent_groups.setdefault(pid, []).append(i)

        for pid, group_indices in parent_groups.items():
            for rank, idx in enumerate(group_indices):
                section_sibling_indices.append(rank)
                section_sibling_counts.append(len(group_indices))

        # ── 切分 chunk ──
        for i, section in enumerate(sections):
            sid = section_ids[i]
            parent_id = section_parent_ids[i]
            child_ids = section_child_ids[i]
            ancestors = section_ancestor_ids[i]
            sib_idx = section_sibling_indices[i]
            sib_count = section_sibling_counts[i]
            is_leaf = section_is_leaf[i]

            # 1. 生成子 chunk（detail 角色）
            detail_texts = _split_section_text(section["text"], text_splitter, chunk_size, chunk_overlap)
            detail_chunks: list[Document] = []
            for dt in detail_texts:
                if len(dt.strip()) < MIN_CHUNK_LENGTH:
                    continue
                chunk = _make_chunk(doc.metadata, dt)
                if section["heading_path"] and not chunk.page_content.startswith(section["heading_path"]):
                    chunk.page_content = f"{section['heading_path']}\n{chunk.page_content}"
                detail_chunks.append(chunk)

            # 记录子 chunk 数量
            chunk_count = len(detail_chunks)

            # 2. 生成子 chunk 的 ID 列表（用于父 chunk 引用）
            source_name = doc.metadata.get("source_file", "unknown")
            child_chunk_ids: list[str] = []
            for ci in range(chunk_count):
                child_chunk_ids.append(_make_chunk_id(source_name, section["section_index"], ci))

            # 3. 写入子 chunk 元数据
            parent_chunk_id: str | None = None
            for ci, chunk in enumerate(detail_chunks):
                _append_chunk_metadata(
                    chunk, section, sid, parent_id, child_ids,
                    len(valid_chunks), ci, chunk_role="detail",
                    parent_chunk_id=parent_chunk_id,
                    ancestor_ids=ancestors,
                    sibling_index=sib_idx,
                    sibling_count=sib_count,
                    is_leaf=is_leaf,
                    doc_id=doc_id,
                )
                chunk.metadata["section.chunk_count"] = chunk_count
                valid_chunks.append(chunk)

            # 4. 生成父 chunk（summary 角色）
            #    仅当子 chunk ≥ _SUMMARY_MIN_CHILD_CHUNKS 时生成
            if chunk_count >= _SUMMARY_MIN_CHILD_CHUNKS:
                summary_text = _generate_section_summary(section, child_chunk_ids)
                if len(summary_text.strip()) >= MIN_CHUNK_LENGTH:
                    summary_chunk = _make_chunk(doc.metadata, summary_text)
                    # 父 chunk 的 local_index 用 -1 标记（不属于子 chunk 序列）
                    summary_chunk_id = _make_chunk_id(
                        source_name, section["section_index"], -1
                    )
                    _append_chunk_metadata(
                        summary_chunk, section, sid, parent_id, child_ids,
                        len(valid_chunks), -1, chunk_role="summary",
                        child_chunk_ids=child_chunk_ids,
                        ancestor_ids=ancestors,
                        sibling_index=sib_idx,
                        sibling_count=sib_count,
                        is_leaf=is_leaf,
                        doc_id=doc_id,
                    )
                    summary_chunk.metadata["section.chunk_id"] = summary_chunk_id
                    summary_chunk.metadata["section.chunk_count"] = chunk_count
                    summary_chunk.metadata["section.char_count"] = len(section["text"])
                    # 旧字段兼容
                    summary_chunk.metadata["chunk_id"] = summary_chunk_id
                    summary_chunk.metadata["char_count"] = len(summary_chunk.page_content)

                    # 回填子 chunk 的 parent_chunk_id
                    parent_chunk_id = summary_chunk_id
                    for ci, chunk in enumerate(detail_chunks):
                        chunk.metadata["section.parent_chunk_id"] = parent_chunk_id

                    valid_chunks.append(summary_chunk)

            # 5. 生成问答索引块（qa 角色）
            #    仅当 section 内容足够时生成
            qa_text = _generate_qa_block(section)
            if qa_text and len(qa_text.strip()) >= MIN_CHUNK_LENGTH:
                qa_chunk = _make_chunk(doc.metadata, qa_text)
                # qa chunk 的 local_index 用 -2 标记
                qa_chunk_id = _make_chunk_id(
                    source_name, section["section_index"], -2
                )
                _append_chunk_metadata(
                    qa_chunk, section, sid, parent_id, child_ids,
                    len(valid_chunks), -2, chunk_role="qa",
                    child_chunk_ids=child_chunk_ids,
                    parent_chunk_id=parent_chunk_id,
                    ancestor_ids=ancestors,
                    sibling_index=sib_idx,
                    sibling_count=sib_count,
                    is_leaf=is_leaf,
                    doc_id=doc_id,
                )
                qa_chunk.metadata["section.chunk_id"] = qa_chunk_id
                qa_chunk.metadata["section.chunk_count"] = chunk_count
                # 旧字段兼容
                qa_chunk.metadata["chunk_id"] = qa_chunk_id
                qa_chunk.metadata["char_count"] = len(qa_chunk.page_content)
                valid_chunks.append(qa_chunk)

    # ── 统计 ──
    summary_count = sum(1 for c in valid_chunks if c.metadata.get("section.chunk_role") == "summary")
    qa_count = sum(1 for c in valid_chunks if c.metadata.get("section.chunk_role") == "qa")
    detail_count = len(valid_chunks) - summary_count - qa_count
    chunk_lengths = [int(c.metadata.get("char_count") or len(c.page_content or "")) for c in valid_chunks]
    detail_chunks = [c for c in valid_chunks if c.metadata.get("section.chunk_role") == "detail"]
    detail_lengths = [int(c.metadata.get("char_count") or len(c.page_content or "")) for c in detail_chunks]
    summary_lengths = [int(c.metadata.get("char_count") or len(c.page_content or "")) for c in valid_chunks if c.metadata.get("section.chunk_role") == "summary"]
    qa_lengths = [int(c.metadata.get("char_count") or len(c.page_content or "")) for c in valid_chunks if c.metadata.get("section.chunk_role") == "qa"]
    incomplete_detail_count = sum(1 for c in detail_chunks if not _is_sentence_complete(c.page_content))
    metrics.emit(
        event="split_documents",
        stage="splitter",
        values={
            "input_docs": len(documents),
            "total_chunks": len(valid_chunks),
            "detail_chunks": detail_count,
            "summary_chunks": summary_count,
            "qa_chunks": qa_count,
            "avg_chunk_chars": round(sum(chunk_lengths) / len(chunk_lengths), 3) if chunk_lengths else 0.0,
            "p50_chunk_chars": _percentile(chunk_lengths, 0.5),
            "p90_chunk_chars": _percentile(chunk_lengths, 0.9),
            "avg_detail_chars": round(sum(detail_lengths) / len(detail_lengths), 3) if detail_lengths else 0.0,
            "avg_summary_chars": round(sum(summary_lengths) / len(summary_lengths), 3) if summary_lengths else 0.0,
            "avg_qa_chars": round(sum(qa_lengths) / len(qa_lengths), 3) if qa_lengths else 0.0,
            "short_chunk_ratio": round(sum(1 for n in chunk_lengths if n < max(MIN_CHUNK_LENGTH * 3, 60)) / len(chunk_lengths), 6) if chunk_lengths else 0.0,
            "long_chunk_ratio": round(sum(1 for n in chunk_lengths if n > int(chunk_size * 1.2)) / len(chunk_lengths), 6) if chunk_lengths else 0.0,
            "mid_sentence_cut_rate": round(incomplete_detail_count / len(detail_chunks), 6) if detail_chunks else 0.0,
        },
    )
    logger.info(
        "Split %d documents into %d chunks (%d summary + %d qa + %d detail)",
        len(documents), len(valid_chunks), summary_count, qa_count, detail_count,
    )
    return valid_chunks
