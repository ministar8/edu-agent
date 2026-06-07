"""异常值检测与处理模块

分两阶段执行，避免重复数据污染统计指标：

阶段1 — 内容层异常（清洗后、去重前执行）：
- 乱码段落定位与隔离（段落级乱码检测，标记而非删除）
- 词频异常（高频重复词，可能为 OCR 伪影或爬虫噪音）
- 全乱码文档过滤（正文几乎全是特殊符号的文档直接标记不入库）

阶段2 — 统计层异常（去重后执行，统计指标更准确）：
- 文本长度离群值（IQR 方法检测过长/过短文档）
- 语言混杂检测（中英文混排比例异常）

处理策略：
- 标记（metadata 标注异常类型与位置）
- 隔离（乱码段落用占位符替换，保留上下文）
- 建议（过长/过短文档给出合并/拆分建议）

原则：宁可误报不可漏报；标记优先于删除；保留可追溯性。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ── 正则预编译 ──────────────────────────────────────

# 中文字符
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")

# 英文字符
_LATIN_RE = re.compile(r"[a-zA-Z]")

# 乱码段落检测：段落中非正常字符占比 > 阈值
# 正常字符 = CJK + CJK标点 + 全角 + ASCII可打印
_NORMAL_CHARS = (
    r"\u4e00-\u9fff" r"\u3400-\u4dbf"   # CJK 汉字
    r"\u3000-\u303f"                      # CJK 标点
    r"\uff00-\uffef"                      # 全角
    r"a-zA-Z0-9"                          # ASCII 字母数字
    r"\s"                                  # 空白
    r"\x20-\x7e"                          # ASCII 可打印
    r".,;:!\?\(\)\[\]\{\}`'\"\-_=/\\\\@#\$%\^&\*\+<>\~"  # 常见标点符号
)
_GARBAGE_CHAR_RE = re.compile(f"[^{_NORMAL_CHARS}]")

# 重复词模式：同一词在短距离内重复3次以上
_REPETITION_RE = re.compile(r"(.{2,8}?)\1{2,}")

# 乱码行特征：行中乱码字符占比 > 40%
_GARBAGE_LINE_RATIO = 0.4

# 全乱码文档阈值：正文乱码字符占比 > 60% 视为全乱码
_FULL_GARBAGE_RATIO = 0.6

# 段落分隔
_PARA_SPLIT_RE = re.compile(r"\n{2,}")


# ── 数据结构 ────────────────────────────────────────

@dataclass
class AnomalyRecord:
    """单文档异常记录"""
    source: str = ""

    # ── 阶段1：内容层 ──
    full_garbage: bool = False                # 全乱码文档（不入库）
    word_freq_anomaly: bool = False           # 词频异常
    word_freq_anomaly_words: list[str] = field(default_factory=list)
    garbled_paragraphs: list[dict] = field(default_factory=list)  # [{"index": int, "position": int, "text": str}]

    # ── 阶段2：统计层 ──
    length_outlier: str | None = None     # "too_short" | "too_long" | None
    length_zscore: float = 0.0               # 长度 Z-Score
    language_mixed: bool = False              # 语言混杂
    language_mix_ratio: float = 0.0           # 中英混排比 (0~1, 越高越混杂)

    # ── 处理标记 ──
    actions_taken: list[str] = field(default_factory=list)


# ── 统计层异常检测 ──────────────────────────────────

def _detect_length_outliers(documents: list[Document]) -> dict[str, tuple[str | None, float]]:
    """基于 IQR 方法检测文本长度离群值

    策略：
    1. 计算所有文档正文长度的 Q1, Q3, IQR
    2. 下界 = Q1 - 1.5*IQR，上界 = Q3 + 1.5*IQR
    3. 低于下界 → too_short，高于上界 → too_long
    4. 同时计算 Z-Score

    Returns:
        {source: (outlier_type, zscore)}
    """
    if len(documents) < 4:
        return {}

    lengths = []
    doc_map: list[tuple[str, int]] = []

    for doc in documents:
        text = doc.page_content.strip() if doc.page_content else ""
        source = str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or id(doc))
        length = len(text)
        lengths.append(length)
        doc_map.append((source, length))

    # 计算 IQR
    sorted_lengths = sorted(lengths)
    n = len(sorted_lengths)
    q1 = sorted_lengths[n // 4]
    q3 = sorted_lengths[3 * n // 4]
    iqr = q3 - q1

    if iqr == 0:
        # 所有文档长度相同，无离群值
        return {}

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    # 计算均值和标准差用于 Z-Score
    mean_len = sum(lengths) / len(lengths)
    variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
    std_len = variance ** 0.5 if variance > 0 else 1.0

    results: dict[str, tuple[str | None, float]] = {}
    for source, length in doc_map:
        zscore = (length - mean_len) / std_len if std_len > 0 else 0.0
        outlier = None
        if length < lower_bound:
            outlier = "too_short"
        elif length > upper_bound:
            outlier = "too_long"
        if outlier:
            results[source] = (outlier, round(zscore, 2))

    return results


def _detect_word_freq_anomaly(text: str, threshold: int = 5) -> tuple[bool, list[str]]:
    """检测词频异常：同一词在短距离内重复出现

    检测模式：
    1. 连续重复词（"的的了了了"）→ 正则匹配
    2. 单字符高频重复（同一字符占正文 > threshold%）

    Args:
        text: 正文文本
        threshold: 单字符占比阈值（百分比），默认 5%

    Returns:
        (是否异常, 异常词列表)
    """
    if not text or len(text) < 20:
        return False, []

    anomaly_words: list[str] = []

    # 1. 连续重复模式检测
    repetitions = _REPETITION_RE.findall(text)
    anomaly_words.extend(repetitions)

    # 2. 单字符高频检测
    from collections import Counter
    # 只统计非空白、非标点字符
    content_chars = [c for c in text if c.strip() and c not in "，。！？：；、""''（）【】《》…—·.,;:!?()[]{}/"]
    if content_chars:
        char_counts = Counter(content_chars)
        total = len(content_chars)
        for char, count in char_counts.most_common(5):
            if count / total * 100 > threshold:
                anomaly_words.append(f"{char}({count}次,{count/total*100:.1f}%)")

    return bool(anomaly_words), anomaly_words[:5]  # 最多返回5个


# ── 内容层异常检测 ──────────────────────────────────

def _detect_full_garbage(text: str) -> bool:
    """检测全乱码文档：正文乱码字符占比超过阈值

    这类文档几乎全是特殊符号，无有效内容，应直接标记不入库。
    """
    if not text or len(text) < 10:
        return False

    garbage_chars = len(_GARBAGE_CHAR_RE.findall(text))
    total_chars = len(text.strip())
    ratio = garbage_chars / max(total_chars, 1)

    return ratio > _FULL_GARBAGE_RATIO


def _detect_language_mixing(text: str, threshold: float = 0.3) -> tuple[bool, float]:
    """检测语言混杂异常

    计算中英文字符占比，当两者都存在且比例接近时判定为混杂。

    Args:
        text: 正文文本
        threshold: 混杂阈值，当 min(cjk_ratio, latin_ratio) > threshold 时判定为混杂

    Returns:
        (是否混杂, 混杂度)
    """
    if not text or len(text) < 50:
        return False, 0.0

    cjk_chars = len(_CJK_RE.findall(text))
    latin_chars = len(_LATIN_RE.findall(text))
    total = cjk_chars + latin_chars

    if total == 0:
        return False, 0.0

    cjk_ratio = cjk_chars / total
    latin_ratio = latin_chars / total

    # 混杂度 = min(cjk_ratio, latin_ratio) * 2，范围 0~1
    # 当两者各占50%时混杂度最高(1.0)，单语言时为0
    mix_degree = min(cjk_ratio, latin_ratio) * 2

    return mix_degree > threshold, round(mix_degree, 3)


def _detect_garbled_paragraphs(text: str, garbage_ratio: float = 0.3) -> list[dict]:
    """检测乱码段落并定位

    策略：
    1. 按空行切分段落
    2. 对每个段落计算乱码字符占比
    3. 占比 > garbage_ratio → 标记为乱码段落
    4. 同时检测行级乱码（行内乱码占比 > 40%）

    Args:
        text: 正文文本
        garbage_ratio: 段落乱码字符占比阈值，默认 30%

    Returns:
        乱码段落列表 [{"index": int, "position": int, "text": str, "garbage_ratio": float}]
    """
    if not text:
        return []

    paragraphs = _PARA_SPLIT_RE.split(text)
    garbled: list[dict] = []
    pos = 0

    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            pos += 2  # \n\n
            continue

        # 计算段落乱码字符占比
        garbage_chars = len(_GARBAGE_CHAR_RE.findall(para))
        total_chars = len(para.strip())
        ratio = garbage_chars / max(total_chars, 1)

        if ratio > garbage_ratio:
            # 截断过长乱码文本用于记录
            preview = para[:100] + "…" if len(para) > 100 else para
            garbled.append({
                "index": i,
                "position": pos,
                "text": preview,
                "garbage_ratio": round(ratio, 3),
            })

        pos += len(para) + 2

    return garbled


# ── 异常处理 ────────────────────────────────────────

def _isolate_garbled_paragraphs(text: str, garbled_paragraphs: list[dict]) -> str:
    """隔离乱码段落：用占位符替换，保留上下文

    替换策略：将乱码段落替换为 "[乱码段落，已隔离，原文N字符]"
    """
    if not garbled_paragraphs:
        return text

    paragraphs = _PARA_SPLIT_RE.split(text)
    garbled_indices = {gp["index"] for gp in garbled_paragraphs}

    result_parts: list[str] = []
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        if i in garbled_indices:
            char_count = len(para)
            result_parts.append(f"[乱码段落，已隔离，原文{char_count}字符]")
        else:
            result_parts.append(para)

    return "\n\n".join(result_parts)


def _clean_repetitions(text: str) -> str:
    """清理连续重复词

    将 "的的的" → "的"，"abcabcabc" → "abc"
    """
    # 多轮清理，处理嵌套重复
    for _ in range(3):
        cleaned = _REPETITION_RE.sub(r"\1", text)
        if cleaned == text:
            break
        text = cleaned
    return text


def _suggest_length_action(outlier_type: str | None, zscore: float) -> str | None:
    """根据长度离群值建议处理操作"""
    if outlier_type == "too_short":
        if zscore < -2.0:
            return "极短文档，建议合并相邻文档或标记为摘要"
        return "偏短文档，建议检查内容完整性"
    elif outlier_type == "too_long":
        if zscore > 3.0:
            return "极长文档，建议拆分为多个子文档后分别入库"
        return "偏长文档，建议优化分块策略"
    return None


# ── 阶段1：内容层异常（清洗后、去重前） ────────────

def detect_content_anomalies(documents: list[Document]) -> tuple[list[Document], list[AnomalyRecord]]:
    """内容层异常检测与处理（阶段1，去重前执行）

    处理明显的"乱码型异常"，避免重复垃圾数据污染后续统计：
    - 全乱码文档过滤（不入库）
    - 乱码段落定位与隔离
    - 词频异常检测 + 重复词清理

    Args:
        documents: 清洗后的文档列表

    Returns:
        (处理后的文档列表, 异常记录列表)
        全乱码文档会被标记 content_status="full_garbage" 但仍保留在列表中，
        由调用方决定是否过滤。
    """
    if not documents:
        return documents, []

    processed_docs: list[Document] = []
    anomaly_records: list[AnomalyRecord] = []
    total_anomalies = 0

    for doc in documents:
        meta = doc.metadata or {}
        source = str(meta.get("source_path") or meta.get("source_file") or id(doc))
        text = doc.page_content.strip() if doc.page_content else ""
        record = AnomalyRecord(source=source)

        # ── 全乱码文档检测 ──
        if _detect_full_garbage(text):
            record.full_garbage = True
            doc.metadata["content_status"] = "full_garbage"
            doc.metadata["garbage_char_ratio"] = round(
                len(_GARBAGE_CHAR_RE.findall(text)) / max(len(text), 1), 3
            )
            record.actions_taken.append("全乱码文档(不入库)")
            total_anomalies += 1
            anomaly_records.append(record)
            processed_docs.append(doc)
            continue

        # ── 乱码段落检测与隔离 ──
        garbled_paras = _detect_garbled_paragraphs(text)
        if garbled_paras:
            record.garbled_paragraphs = garbled_paras
            doc.metadata["garbled_paragraphs"] = len(garbled_paras)
            doc.metadata["garbled_paragraph_indices"] = [gp["index"] for gp in garbled_paras]

            # 隔离乱码段落（替换为占位符，保留上下文）
            isolated_text = _isolate_garbled_paragraphs(text, garbled_paras)
            if isolated_text != text:
                doc.page_content = isolated_text
                doc.metadata["garbled_isolated"] = True
                record.actions_taken.append(f"隔离{len(garbled_paras)}个乱码段落")
            total_anomalies += 1

        # ── 词频异常检测 ──
        is_anomaly, anomaly_words = _detect_word_freq_anomaly(text)
        if is_anomaly:
            record.word_freq_anomaly = True
            record.word_freq_anomaly_words = anomaly_words
            doc.metadata["word_freq_anomaly"] = True
            doc.metadata["word_freq_anomaly_words"] = anomaly_words

            # 清理连续重复词
            cleaned_text = _clean_repetitions(text)
            if len(cleaned_text) < len(text):
                reduction = len(text) - len(cleaned_text)
                doc.page_content = cleaned_text
                doc.metadata["repetition_cleaned"] = reduction
                record.actions_taken.append(f"清理重复词(减少{reduction}字符)")
            total_anomalies += 1

        # ── 记录异常元数据 ──
        has_anomaly = bool(record.actions_taken)
        doc.metadata["has_content_anomaly"] = has_anomaly
        if has_anomaly:
            doc.metadata["_content_anomaly_log"] = record.actions_taken

        anomaly_records.append(record)
        processed_docs.append(doc)

    # ── 汇总日志 ──
    if total_anomalies > 0:
        anomaly_types: dict[str, int] = {}
        for rec in anomaly_records:
            if rec.full_garbage:
                anomaly_types["full_garbage"] = anomaly_types.get("full_garbage", 0) + 1
            if rec.garbled_paragraphs:
                anomaly_types["garbled_para"] = anomaly_types.get("garbled_para", 0) + 1
            if rec.word_freq_anomaly:
                anomaly_types["word_freq"] = anomaly_types.get("word_freq", 0) + 1

        summary = ", ".join(f"{k}:{v}" for k, v in sorted(anomaly_types.items()))
        logger.info(
            "Anomaly[阶段1/内容层]: %d anomalies across %d docs — %s",
            total_anomalies,
            sum(1 for r in anomaly_records if r.actions_taken),
            summary,
        )

    return processed_docs, anomaly_records


# ── 阶段2：统计层异常（去重后） ────────────────────

def detect_statistical_anomalies(documents: list[Document], prev_records: list[AnomalyRecord] | None = None) -> tuple[list[Document], list[AnomalyRecord]]:
    """统计层异常检测与处理（阶段2，去重后执行）

    去重后数据更干净，统计指标更准确：
    - 文本长度离群值（IQR 方法）
    - 语言混杂检测

    Args:
        documents: 去重后的文档列表
        prev_records: 阶段1的异常记录（用于合并）

    Returns:
        (处理后的文档列表, 合并后的异常记录列表)
    """
    if not documents:
        return documents, prev_records or []

    # ── 统计层：长度离群值（需要全量去重后数据） ──
    length_outliers = _detect_length_outliers(documents)

    # 构建 source → record 映射（用于合并阶段1记录）
    record_map: dict[str, AnomalyRecord] = {}
    if prev_records:
        for rec in prev_records:
            record_map[rec.source] = rec

    processed_docs: list[Document] = []
    all_records: list[AnomalyRecord] = []
    total_anomalies = 0

    for doc in documents:
        meta = doc.metadata or {}
        source = str(meta.get("source_path") or meta.get("source_file") or id(doc))
        text = doc.page_content.strip() if doc.page_content else ""

        # 合并或新建记录
        record = record_map.get(source, AnomalyRecord(source=source))

        # ── 统计层：长度离群值 ──
        if source in length_outliers:
            outlier_type, zscore = length_outliers[source]
            record.length_outlier = outlier_type
            record.length_zscore = zscore
            doc.metadata["length_outlier"] = outlier_type
            doc.metadata["length_zscore"] = zscore
            suggestion = _suggest_length_action(outlier_type, zscore)
            if suggestion:
                doc.metadata["length_suggestion"] = suggestion
                record.actions_taken.append(f"标记长度异常({outlier_type}, z={zscore})")
            total_anomalies += 1

        # ── 统计层：语言混杂检测 ──
        is_mixed, mix_ratio = _detect_language_mixing(text)
        if is_mixed:
            record.language_mixed = True
            record.language_mix_ratio = mix_ratio
            doc.metadata["language_mixed"] = True
            doc.metadata["language_mix_ratio"] = mix_ratio
            record.actions_taken.append(f"标记语言混杂(混排度={mix_ratio:.1%})")
            total_anomalies += 1

        # ── 记录异常元数据 ──
        has_anomaly = bool(record.actions_taken)
        doc.metadata["has_anomaly"] = has_anomaly
        if has_anomaly:
            doc.metadata["_anomaly_log"] = record.actions_taken

        all_records.append(record)
        processed_docs.append(doc)

    # ── 汇总日志 ──
    if total_anomalies > 0:
        anomaly_types: dict[str, int] = {}
        for rec in all_records:
            if rec.length_outlier:
                anomaly_types[f"length_{rec.length_outlier}"] = anomaly_types.get(f"length_{rec.length_outlier}", 0) + 1
            if rec.language_mixed:
                anomaly_types["language_mixed"] = anomaly_types.get("language_mixed", 0) + 1

        summary = ", ".join(f"{k}:{v}" for k, v in sorted(anomaly_types.items()))
        logger.info(
            "Anomaly[阶段2/统计层]: %d anomalies across %d docs — %s",
            total_anomalies,
            sum(1 for r in all_records if r.actions_taken),
            summary,
        )

    return processed_docs, all_records


# ── 兼容旧接口 ────────────────────────────────────

def detect_anomalies(documents: list[Document]) -> tuple[list[Document], list[AnomalyRecord]]:
    """异常值检测与处理（兼容接口，内部自动分两阶段）

    对于不关心两阶段分离的调用方，提供单入口便捷函数。
    """
    # 阶段1：内容层
    docs, records = detect_content_anomalies(documents)

    # 过滤全乱码文档（不入库）
    docs = [d for d in docs if d.metadata.get("content_status") != "full_garbage"]

    # 阶段2：统计层
    docs, records = detect_statistical_anomalies(docs, prev_records=records)

    return docs, records
