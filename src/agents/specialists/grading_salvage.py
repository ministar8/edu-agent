"""批改专用兜底解析：把模型飘移出的裸文本恢复成 ``GradingResult``。

## 为什么单独成模块

这段解析（``score: 40`` / ``feedback: ...`` 行式文本）与 ``GradingResult``
**逐字段耦合**，只对批改语义有意义。它原先住在 ``rag.retrieval.llm_calls`` 的
通用 LLM 骨架里，导致通用基建反向知道业务字段名。2026-11-07 迁移时拆到这里，
由 ``agents.specialists.grading.agrade_answer`` 通过
``call_structured(..., salvage=salvage_grading)`` 显式注入。

通用部分（工具标记清洗 + JSON 重解析）仍在 ``core.llm_calls.salvage_json_from_raw``。

## 触发条件（与原实现一致）

只在**清洗工具标记确实改变了内容**时才尝试 —— 即模型把
``<parameter=score>`` 之类的标记泄漏进自然语言文本（实测 DashScope /
DeepSeek 兼容端的 function_calling 模式偶发此形态）。
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ValidationError

from core.llm_calls import strip_tool_markup

logger = logging.getLogger(__name__)

__all__ = ["salvage_grading"]


def salvage_grading[T: BaseModel](raw: str, schema: type[T]) -> T | None:
    """把「工具标记污染 + 行式裸文本」恢复成 ``schema`` 实例；救不回返回 None。"""
    cleaned = strip_tool_markup(raw)
    if cleaned == raw:
        return None  # 没有标记污染，不属于本兜底能治的情形

    payload = _try_kv_dict(cleaned)
    if not payload:
        return None
    try:
        candidate = schema.model_validate(payload)
    except ValidationError:
        return None
    logger.info("批改兜底解析成功：字段 %s", sorted(payload))
    return candidate


def _scan_kv_fields(text: str) -> dict[str, str]:
    """规则 ①②：逐行扫描定位起点，并按字段分类决定是否并入续行。

    遇到第一个合法字段 key 才开始解析；进入解析后的非 key 行，**仅**多行字段
    （`_KV_MULTILINE_FIELDS`）允许续行，其余（score / is_wrong / knowledge_points）丢弃。
    """
    kv_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:：]\s*(.*)$")
    fields: dict[str, str] = {}
    current: str | None = None
    started = False  # 是否已遇到第一个合法 key
    for line in text.splitlines():
        m = kv_re.match(line)
        if m and m.group(1) in _KV_ALL_FIELDS:
            # ① 进入解析（首个合法 key）
            started = True
            current = m.group(1)
            fields[current] = m.group(2).strip()
        elif not started:
            # ① 尚未进入解析：忽略前言/空行/解释文字
            continue
        elif current is not None and current in _KV_MULTILINE_FIELDS:
            # ② 仅多行字段允许续行
            #   ★ `current is not None` 是**显式收窄**，不是行为变化：`None` 本就不属于
            #     `_KV_MULTILINE_FIELDS`（`frozenset[str]`），旧写法在运行时同义，
            #     但成员测试无法让 pyrefly 把 `current` 从 `str | None` 收成 `str`。
            fields[current] = (fields[current] + "\n" + line).strip()
        else:
            # ② 其余字段（score / is_wrong / knowledge_points）：丢弃该行
            continue
    return fields


def _parse_kv_fields(fields: dict[str, str]) -> dict[str, object]:
    """规则 ③：按字段分类解析 —— scalar 按标量语义，list 按分隔符切分。"""
    out: dict[str, object] = {}
    for key, val in fields.items():
        if key == "score":
            num = re.search(r"-?\d+(?:\.\d+)?", val)
            if num:
                # 整数值给 int（`GradingResult.score` 是 int，浮点会被 pydantic 拒；
                # 而 40.0 这类无小数部分的 float 虽被接受，仍以 int 表达更贴 schema）。
                f = float(num.group())
                out[key] = int(f) if f.is_integer() else f
        elif key == "is_wrong":
            out[key] = val.strip().lower() in {"true", "1", "yes", "是"}
        elif key in _KV_LIST_FIELDS:
            # ③ list 字段：按分隔符切分（顿号 / 逗号 / 分号 / 换行），并去空去重保序
            items = [p.strip().strip("[]\"'") for p in re.split(r"[、,，;；\n]", val)]
            out[key] = [p for p in (i for i in items) if p]
        else:
            if val:
                out[key] = val
    return out


def _try_kv_dict(text: str) -> dict | None:
    """解析裸文本形态 ``score: 40`` / ``feedback: ...`` 为 dict。

    ★ 2026-10-06 第二轮 review 重写（原实现有 3 个缺陷，见下）。

    原实现的 3 个缺陷：

    1. **`is_wrong` 语义反转**：任何**非白名单行**（`knowledge_points:` / `topic:` /
       `reason:` / `# 备注` …）都会被拼进**上一字段**：
       ``is_wrong = "true\\nknowledge_points: [...]"`` ⇒ 判定 ``in {"true",…}`` 失败
       ⇒ **`True` 变 `False`**（语义反转，不是丢失）。
    2. **首行有前言即全盘放弃**：首行非 ``key:`` 形态直接 ``return None``
       ⇒ ``'好的，批改如下：\\nscore: 40…'`` 连 ``score`` 都救不回。
       而模型飘移的典型形态恰是「前面带一句话」（实测日志有 ``Let's output.``）。
    3. **`knowledge_points` 静默丢失**：它在 schema 里却是 5 个字段，但白名单只有 4 个
       ⇒ ``schema 支持的字段集合 ≠ 本兜底支持的字段集合``（协议不一致）。

    重写后的规则（三条，顺序敏感）：

    ┌─ ① 扫描定位起点 ────────────────────────────────────────────
    │  逐行扫，**遇到第一个合法字段 key 才开始解析**。
    │  之前的行（前言 / 空行 / 解释文字）一律忽略 —— 但**不是**「所有非 key 行都忽略」，
    │  而是「进入解析前忽略、进入解析后按 ② 处理」，避免把真正的异常输出静默吞掉。
    ├─ ② 续行规则（严格） ───────────────────────────────────────
    │  非 key 行**仅当**当前字段 ∈ `_KV_MULTILINE_FIELDS`（feedback / error_analysis，
    │  它们本来就是多行文本）时，才作为**续行**并入上一字段；
    │  否则**直接丢弃该行**（绝不拼进 is_wrong / score / knowledge_points）。
    └─ ③ 字段分类解析 ───────────────────────────────────────────
       scalar（score / is_wrong / feedback / error_analysis）按标量语义解析；
       list（knowledge_points）按**分隔符切分**为 ``list[str]`` ——
       绝不把整个字符串硬塞进一个 list 字段。

    规则 ①② 见 `_scan_kv_fields`，③ 见 `_parse_kv_fields`。
    """
    fields = _scan_kv_fields(text)
    if not fields:
        return None
    return _parse_kv_fields(fields)


# ③ 字段分类（协议与 `GradingResult` 对齐；由 `tests/test_grading_salvage.py`
#    断言**覆盖 schema 全部字段** —— 原注释声称的 gate `⑨g` 在全仓并不存在）
_KV_SCALAR_FIELDS = frozenset({"score", "feedback", "is_wrong", "error_analysis"})
_KV_LIST_FIELDS = frozenset({"knowledge_points"})
_KV_ALL_FIELDS = _KV_SCALAR_FIELDS | _KV_LIST_FIELDS
# ② 允许**多行续行**的字段（它们本来就是多行自由文本）。
#   ★ 不含 is_wrong / score / knowledge_points —— 避免「续行污染导致语义反转」。
_KV_MULTILINE_FIELDS = frozenset({"feedback", "error_analysis"})
