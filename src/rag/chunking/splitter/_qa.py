"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

import re

# ── 结构化分块：语义单元解析 ────────────────────────

# 列表项正则：- 开头 或 数字. 开头
_LIST_ITEM_RE = re.compile(r"^(?:[-*+]|\d+[.．])\s+", re.MULTILINE)


# ── Q&A 单元识别正则 ──────────────────────────────────
# 例题模式：> 例题 / > 例N / > 例1：
_EXAMPLE_Q_RE = re.compile(r"^>\s*(?:例[题\d]|例\d+[：:])", re.MULTILINE)

# ── 答案标记（仅「词 + 冒号」形态）────────────────────
# 认 `解答：` / `答案：` / `正确答案：` / `**解析**：`（加粗夹在词与冒号之间）。
# ★ 2026-10 语料重建后**移除两处旧真题格式支持**（实测 knowledge/ 全库 0 命中）：
#   · 行尾 `✅` 标正确选项 —— 新格式把答案改存 metadata 的 `answer_key`；
#   · `##### N` / `### 第N题` 真题标题 —— 新格式改用 `## YYYY-QN`，且 ingest 直接
#     按题构造 Document，不再需要 splitter 猜。二者皆成死代码；且「真题模式」若生效
#     会把题+答合并成一个 chunk，与 L3「items/answer 分开」的设计直接冲突。
_ANSWER_RE = re.compile(
    r"(?:解答|答案|正确答案|解析)[ \t]*\**[ \t]*[：:；;]",
    re.MULTILINE,
)

# 答案字母提取：`正确答案：D` / `答案：B`。
_ANSWER_KEY_RE = re.compile(
    r"(?:正确答案|答案)[：:；;]\s*([A-E](?:,[A-E])*)",
    re.MULTILINE,
)

# 非选择题的 answer_key：取「答案:/解答:」之后到 ; 或行尾的内容
_NON_LETTER_KEY_RE = re.compile(r"(?:答案|解答)[：:；;]\s*(.+?)(?:[；;]|$)", re.MULTILINE)


def _merge_qa_blockquotes(text: str) -> str:
    """预扫描文本，把「例题」blockquote 区域合并为原子块。

    例题模式：`> 例题` / `> 例N` 开头，到 `答案：`/`解答：`/`正确答案：` 结束。
    合并后的块以 `__QA_PAIR_START__` 标记，后续 `_parse_semantic_units` 识别为原子单元。

    ★ 2026-10 移除「真题模式」分支（`##### N` / `### 第N题`）：新语料 0 命中，
    且 L3 由 ingest 按题构造 Document（items / answer 各自成 chunk），不走此合并。
    """
    lines = text.splitlines()
    result_lines: list[str] = []
    qa_buffer: list[str] = []
    in_qa = False

    for line in lines:
        stripped = line.strip()

        # ── 检测例题开头 ──
        if _EXAMPLE_Q_RE.match(line):
            if in_qa and qa_buffer:
                result_lines.append("__QA_PAIR_START__" + "\n".join(qa_buffer))
                qa_buffer = []
            in_qa = True
            qa_buffer.append(line)
            continue

        if in_qa:
            if stripped.startswith(">") or _ANSWER_RE.search(stripped):
                qa_buffer.append(line)
            else:
                # 非引用行出现，关闭当前 QA 块
                result_lines.append("__QA_PAIR_START__" + "\n".join(qa_buffer))
                qa_buffer = []
                in_qa = False
                result_lines.append(line)
        else:
            result_lines.append(line)

    # 处理未关闭的 QA buffer
    if in_qa and qa_buffer:
        result_lines.append("__QA_PAIR_START__" + "\n".join(qa_buffer))

    return "\n".join(result_lines)


def _restore_code_placeholders(text: str, code_blocks: list[str]) -> str:
    """将代码块占位符还原为实际代码"""

    def _restore(m: re.Match) -> str:
        idx = int(m.group(1))
        if 0 <= idx < len(code_blocks):
            return code_blocks[idx]
        return m.group(0)

    return re.sub(r"__CODE_BLOCK_(\d+)__", _restore, text)


def _extract_qa_fields(text: str) -> dict:
    """从 Q&A 文本中提取结构化字段

    Returns:
        {
            "question": str,    # 题干部分（答案之前的文本）
            "answer": str,      # 答案+解析部分（从答案标记开始）
            "answer_key": str,  # 正确答案：选择题为字母(A-E)，计算/简答题为答案摘要
        }
    """
    # 提取答案标识：先尝试字母(A-E)，失败则提取答案:后到分号/行尾的内容
    key_match = _ANSWER_KEY_RE.search(text)
    if key_match:
        answer_key = key_match.group(1)
    else:
        # 非选择题：提取 答案:XXX 或 解答:XXX 中到 ; 或行尾的部分
        nl_match = _NON_LETTER_KEY_RE.search(text)
        answer_key = nl_match.group(1).strip()[:120] if nl_match else ""
    answer_key = re.sub(r"^>\s*", "", answer_key, flags=re.MULTILINE)
    answer_key = re.sub(r"\*{1,2}", "", answer_key).strip()

    answer_match = _ANSWER_RE.search(text)
    if answer_match:
        question = text[: answer_match.start()].strip()
        answer = text[answer_match.start() :].strip()
    else:
        question = text.strip()
        answer = ""

    question = re.sub(r"^>\s*", "", question, flags=re.MULTILINE)
    question = re.sub(r"^例[题\d]+[：:]?\s*", "", question, count=1)
    question = question.strip()

    answer = re.sub(r"^(?:正确)?(?:答案|解答)[：:；;]\s*", "", answer, count=1)
    answer = answer.strip()

    return {
        "question": question,
        "answer": answer,
        "answer_key": answer_key,
    }
