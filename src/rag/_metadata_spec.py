"""元数据字段规范

统一所有模块的 metadata 字段命名、类型和语义。
所有 chunk/document 的 metadata 必须遵循此规范。

命名空间约定：
  source.*    — 来源信息（loader 写入）
  section.*   — 层级结构（splitter 写入）
  content.*   — 内容属性（enhancer 写入）
  quality.*   — 质量标记（anomaly/imputer 写入）
  recall.*    — 检索评分（retriever/reranker 写入，不入库）

层级化切分字段（section.*）：
  section.id              — section 唯一标识
  section.parent_id       — 父 section 的 id（顶级 section 为 None）
  section.child_ids       — 子 section 的 id 列表（JSON 字符串）
  section.depth           — 层级深度（0=文档级, 1=章, 2=节, 3=小节）
  section.path            — 标题路径 "章1 > 节1.1 > 小节1.1.1"
  section.title           — 当前 section 标题
  section.heading_level   — Markdown 标题层级（1-6，0=无标题）
  section.index           — 同级 section 中的序号
  section.char_count      — section 总字符数
  section.chunk_count     — section 内子 chunk 数量

Chunk 级字段（section.* 续）：
  section.chunk_id        — chunk 唯一标识
  section.chunk_parent_id — 所属 section 的 id
  section.chunk_index     — section 内 chunk 序号（0-based）
  section.chunk_role      — chunk 角色："detail"(细粒度) / "summary"(摘要)
"""

from __future__ import annotations

# ── 字段定义 ──────────────────────────────────────────
# (field_name, type_hint, description, writer_module)

FIELDS: list[tuple[str, str, str, str]] = [
    # ── source.* — 来源信息 ──
    ("source_file",          "str",   "文件名（含扩展名）",                    "loader"),
    ("source_path",          "str",   "相对路径",                              "loader"),
    ("source_ext",           "str",   "扩展名（小写，含.）",                   "loader"),
    ("source_type",          "str",   "文件类型（无.）",                       "loader"),
    ("source_name",          "str",   "文件名（无扩展名）",                    "enhancer"),
    ("detected_encoding",    "str",   "自动检测到的编码",                      "loader"),

    # ── section.* — 层级结构 ──
    ("section.doc_id",       "str",         "文档级唯一标识",                "splitter"),
    ("section.id",           "str|None",    "section 唯一标识",                "splitter"),
    ("section.parent_id",    "str|None",    "父 section id",                  "splitter"),
    ("section.child_ids",    "str",         "子 section id 列表(JSON)",       "splitter"),
    ("section.ancestor_ids", "str",         "祖先链 ID 列表(JSON, 根→父)",   "splitter"),
    ("section.depth",        "int",         "层级深度 0/1/2/3",              "splitter"),
    ("section.path",         "str",         "标题路径 [章>节>小节]",          "splitter"),
    ("section.title",        "str",         "当前 section 标题",              "splitter"),
    ("section.heading_level","int",         "Markdown 标题层级 0-6",         "splitter"),
    ("section.index",        "int",         "同级 section 序号",              "splitter"),
    ("section.sibling_index", "int",        "同级兄弟中的序号(0-based)",      "splitter"),
    ("section.sibling_count", "int",        "同级兄弟总数",                    "splitter"),
    ("section.is_leaf",      "bool",        "是否为叶子 section(无子 section)", "splitter"),
    ("section.char_count",   "int",         "section 总字符数",               "splitter"),
    ("section.chunk_count",  "int",         "section 内子 chunk 数",          "splitter"),
    ("section.chunk_id",     "str",         "chunk 唯一标识",                 "splitter"),
    ("section.chunk_parent_id", "str",      "chunk 所属 section id",          "splitter"),
    ("section.chunk_index",  "int",         "section 内 chunk 序号",          "splitter"),
    ("section.chunk_role",   "str",         "chunk 角色: detail/summary/qa/merged_qa",     "splitter"),
    ("section.child_chunk_ids", "str",      "父 chunk 引用的子 chunk ID 列表(JSON)", "splitter"),
    ("section.parent_chunk_id", "str|None", "子 chunk 引用的父 chunk ID",     "splitter"),
    # ── qa.* — Q&A 结构化字段（merged_qa 角色专用，存储合并检索分离） ──
    ("qa.question",         "str",   "题干部分（答案之前的文本）",       "splitter"),
    ("qa.answer",           "str",   "答案+解析部分（从答案标记开始）",  "splitter"),
    ("qa.answer_key",       "str",   "正确答案字母 A/B/C/D/E",          "splitter"),


    # ── content.* — 内容属性 ──
    ("content_type",         "str",   "内容类型: text/section/list/code_mixed/exercise/answer/merged_qa/empty", "enhancer"),
    ("content_status",       "str",   "内容状态: normal/empty/placeholder/truncated/full_garbage",     "imputer/anomaly"),
    ("keywords",             "str",   "关键词逗号分隔",                        "enhancer"),
    ("keyword_list",         "list",  "关键词列表（不入 Chroma，仅内部使用）",  "enhancer"),
    ("heading_keywords",     "str",   "标题关键词逗号分隔",                    "enhancer"),
    ("heading_keyword_list", "list",  "标题关键词列表（不入 Chroma）",          "enhancer"),
    ("heading_slug",         "str",   "标题路径 slug: python/装饰器/闭包",     "enhancer"),
    ("has_heading",          "bool",  "是否有标题",                            "enhancer/imputer"),
    ("has_code_block",       "bool",  "是否含代码块",                          "enhancer"),
    ("has_auto_sections",    "bool",  "是否自动分段",                          "imputer"),
    ("has_placeholder",      "bool",  "是否含占位符",                          "imputer"),
    ("truncated",            "bool",  "是否截断",                              "imputer"),
    ("is_structured",        "bool",  "是否结构化内容",                        "enhancer"),
    ("line_count",           "int",   "行数",                                  "enhancer"),
    ("estimated_tokens",     "int",   "估算 token 数",                         "enhancer"),
    ("char_count",           "int",   "chunk 字符数",                          "splitter/enhancer"),
    ("category",             "str",   "文档分类",                              "imputer/ingest"),

    # ── quality.* — 质量标记 ──
    ("normalized",              "bool",  "是否已标准化",                        "normalizer"),
    ("normalization_changes",   "list",  "标准化变更列表",                      "normalizer"),
    ("heading_level_jumps",     "list",  "标题层级跳跃",                        "normalizer"),
    ("cleaned_ratio",           "str",   "清洗比例",                            "cleaner"),
    ("heading_source",          "str",   "标题推断方法",                        "imputer"),
    ("heading_confidence",      "str",   "标题推断置信度: high/medium/low",     "imputer"),
    ("garbage_char_ratio",      "float", "乱码字符占比",                        "anomaly"),
    ("garbled_paragraphs",      "int",   "乱码段落数",                          "anomaly"),
    ("garbled_paragraph_indices","list",  "乱码段落索引",                        "anomaly"),
    ("garbled_isolated",        "bool",  "乱码段落已隔离",                      "anomaly"),
    ("word_freq_anomaly",       "bool",  "词频异常",                            "anomaly"),
    ("word_freq_anomaly_words", "list",  "词频异常词列表",                      "anomaly"),
    ("repetition_cleaned",      "int",   "清理重复词减少字符数",                "anomaly"),
    ("has_content_anomaly",     "bool",  "是否有内容层异常",                    "anomaly"),
    ("has_anomaly",             "bool",  "是否有统计层异常",                    "anomaly"),
    ("length_outlier",          "str",   "长度离群类型: short/long/normal",     "anomaly"),
    ("length_zscore",           "float", "长度 Z-Score",                        "anomaly"),
    ("length_suggestion",       "str",   "长度异常建议",                        "anomaly"),
    ("language_mixed",          "bool",  "语言混杂",                            "anomaly"),
    ("language_mix_ratio",      "float", "语言混排度",                          "anomaly"),
    ("content_hash",            "str",   "内容哈希（去重用）",                  "vectorstore"),

    # ── recall.* — 检索评分（运行时，不入库） ──
    ("recall_score",   "float", "召回评分",    "retriever"),
    ("recall_routes",  "str",   "召回路径",    "retriever"),
    ("rerank_score",   "float", "重排序评分",  "reranker"),

    # ── 内部审计（不入 Chroma） ──
    ("_impute_log",          "list", "填充审计日志",     "imputer"),
    ("_content_anomaly_log", "list", "内容异常日志",     "anomaly"),
    ("_anomaly_log",         "list", "统计异常日志",     "anomaly"),
    ("auto_sections",        "list", "自动分段结果",     "imputer"),
]

# ── Chroma 不支持的类型 → 转换规则 ──
# Chroma metadata 只支持 str/int/float/bool
# list 类型字段不入库，仅在内存中使用
CHROMA_EXCLUDED_FIELDS = frozenset({
    "keyword_list",
    "heading_keyword_list",
    "normalization_changes",
    "heading_level_jumps",
    "garbled_paragraph_indices",
    "word_freq_anomaly_words",
    "_impute_log",
    "_content_anomaly_log",
    "_anomaly_log",
    "auto_sections",
})

# ── 旧字段 → 新字段 映射（兼容迁移） ──
LEGACY_FIELD_MAP: dict[str, str] = {
    "heading":            "section.path",
    "heading_title":      "section.title",
    "heading_level":      "section.heading_level",
    "heading_path":       "section.path",
    "section_index":      "section.index",
    "chunk_id":           "section.chunk_id",
    "chunk_index":        "section.chunk_index",
    "chunk_index_in_section": "section.chunk_index",
}


def migrate_metadata(metadata: dict) -> dict:
    """将旧字段名迁移为新规范字段名

    保留旧字段以兼容，同时写入新字段。
    """
    for old_key, new_key in LEGACY_FIELD_MAP.items():
        if old_key in metadata and new_key not in metadata:
            metadata[new_key] = metadata[old_key]
    return metadata


def sanitize_for_chroma(metadata: dict) -> dict:
    """清理 metadata 中 Chroma 不支持的类型字段

    移除 list 类型字段和内部审计字段，保留可入库的字段。
    """
    return {
        k: v for k, v in metadata.items()
        if k not in CHROMA_EXCLUDED_FIELDS
        and not k.startswith("_")
        and isinstance(v, (str, int, float, bool))
    }
