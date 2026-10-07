"""RAG 层统一的 LLM 调用入口。

此前 7 处调用各写一遍「取客户端 → 调用 → 解析 → 失败兜底」，导致两个问题：
超时只有 decomposer 显式施加，失败语义有三种（返回空串 / 返回原顺序 / 抛 500）。

本模块把骨架收敛到一处，并统一约定：

- **失败（含超时、解析失败）一律返回 ``None``**，由调用方显式决定降级方向，
  不再由被调方替调用方决定"失败就该给空串"。
- 异步版本统一用 ``asyncio.wait_for`` 施加超时；同步版本供同步上下文（如 ingest
  后的缓存预热）使用，超时由客户端级 ``request_timeout`` 兜底。
"""

from __future__ import annotations

import asyncio
import logging
import re

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

from core.llm import get_llm
from core.settings import settings
from prompts import PROMPT_SET_VERSION

logger = logging.getLogger(__name__)

# 既接受裸字符串（会被包成单条 HumanMessage），也接受 ChatPromptTemplate
# 产出的消息列表（指令进 SystemMessage、数据进 HumanMessage）。
type PromptInput = str | list[BaseMessage]

# ★ 2026-10-06（Step 5 实测）：模型在 function_calling 模式下**格式飘移**时，会把
#   工具调用的参数标记直接吐进自然语言文本，实测见过三种形态：
#
#       "结构描述基本正确……\n<parameter=score>\n95"
#       "……<parameter=feedback>平衡性判断有误</parameter>"
#       "……AVL树\n\n\n<tool_call>"
#
#   这些标记**不是**批改内容，却占了长度、污染了字段语义。清洗掉再交给 Pydantic，
#   能把「格式飘移」与「真错误答案」区分开 —— 前者不该让整条链路判失败。
#   只匹配工具调用相关的成对/自闭合标签，不碰正文里正常的尖括号（如泛型 <T>）。
_TOOL_MARKUP_RE = re.compile(
    r"</?(?:parameter|tool_call|tool_calls|function_call|function|invoke)"
    r"(?:\s*=\s*[^>]*)?>",
    re.IGNORECASE,
)


def _strip_tool_markup(text: str) -> str:
    """剥掉泄漏进自然语言输出里的工具调用标记（含其后的孤立闭合标记）。"""
    if not text or "<" not in text:
        return text
    return _TOOL_MARKUP_RE.sub("", text).strip()


def _as_text(raw: object) -> str:
    content = getattr(raw, "content", raw)
    return str(content).strip()


def _trace_config(stage: str) -> dict:
    """把提示词阶段与提示词集版本写进 run metadata。

    LangSmith 据此按提示词分组 —— 改过提示词后输出质量变化可直接归因。
    """
    return {"metadata": {"prompt_stage": stage, "prompt_set_version": PROMPT_SET_VERSION}}


def _log_failure(stage: str, exc: BaseException) -> None:
    logger.warning("LLM call failed [%s]: %s: %s", stage, type(exc).__name__, exc)


async def call_text(
    prompt: PromptInput,
    *,
    temperature: float,
    timeout: float,
    stage: str,
) -> str | None:
    """调用 LLM 取纯文本。超时或异常返回 None。"""
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        raw = await asyncio.wait_for(
            llm.ainvoke(prompt, config=_trace_config(stage)), timeout=timeout
        )
    except Exception as exc:
        _log_failure(stage, exc)
        return None
    return _as_text(raw)


def call_text_sync(
    prompt: PromptInput,
    *,
    temperature: float,
    stage: str,
) -> str | None:
    """``call_text`` 的同步版本，**仅供同步上下文使用**（如 ingest 的缓存预热）。

    注意：在 ``async def`` 里直接调用它会阻塞事件循环整个 LLM 调用时长；
    async 上下文请用 ``await call_text(...)``。
    """
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        raw = llm.invoke(prompt, config=_trace_config(stage))
    except Exception as exc:
        _log_failure(stage, exc)
        return None
    return _as_text(raw)


def _bind_structured(llm, schema: type):
    """按配置绑定 with_structured_output；失败时回退不带 method 的默认实现。"""
    method = settings.STRUCTURED_OUTPUT_METHOD
    try:
        return llm.with_structured_output(schema, method=method)
    except Exception as exc:
        logger.warning("with_structured_output(method=%s) 失败，回退默认: %s", method, exc)
        return llm.with_structured_output(schema)


async def call_structured[T: BaseModel](
    prompt: PromptInput,
    schema: type[T],
    *,
    temperature: float,
    timeout: float,
    stage: str,
) -> T | None:
    """调用 LLM 并解析为结构化结果。超时、异常或结构不符均返回 None。

    ★ 2026-10-06（Step 5 实测）：**对可重试的结构化失败做同 prompt 重试**。

    背景：实测 DashScope 兼容端即使强制 ``tool_choice``，仍**偶发**返回裸文本
    （形如 ``score: 40\\nfeedback: ...``）而非 tool call 参数。这类输出的长度不受
    schema 约束，一旦超过 ``max_length``，Pydantic 校验即抛 ``ValidationError``。
    此前该异常被本函数的 ``except Exception`` 吞成 ``None``，调用方（如
    ``grading_core.agrade_answer``）无法区分「上游超时」与「只是这一次格式飘了」，
    只能整体判失败 —— 批改链路因此**随机整体崩塌**。

    因此：**第一次失败后按 ``STRUCTURED_OUTPUT_RETRIES`` 重试**（同 prompt、
    同 temperature）。重试是安全的 —— 失败不产生副作用（纯读），而实测同 prompt
    重试的成功率提升显著（第一次裸文本、第二次常回正常 tool call）。

    ``timeout`` 语义：**单次尝试**的上限，不是总时长。总耗时上界为
    ``(1 + STRUCTURED_OUTPUT_RETRIES) * timeout``；调用方如需严格总预算，
    应在外层再包一层 ``asyncio.wait_for``。

    ★ 兜底清洗：若重试耗尽仍失败，且**最后一次的原始输出可拿到**，则尝试
      ``_strip_tool_markup`` + 重新解析（§ ``_salvage_from_raw``）。仅当该次失败
      确实是「工具标记污染了文本字段」时才可能救回；救不回仍返回 ``None``。
    """
    llm = get_llm(streaming=False, temperature=temperature)
    attempts = max(1, 1 + int(settings.STRUCTURED_OUTPUT_RETRIES))
    last_exc: BaseException | None = None
    last_raw: str = ""
    for attempt in range(attempts):
        try:
            structured = _bind_structured(llm, schema)
            result = await asyncio.wait_for(
                structured.ainvoke(prompt, config=_trace_config(stage)), timeout=timeout
            )
        except Exception as exc:
            last_exc = exc
            # 格式飘移时异常里带的是「原始文本」，取回留作兜底素材。
            raw_text = _raw_from_validation_error(exc)
            if raw_text:
                last_raw = raw_text
            # 超时不可重试：重试只会再等一个 timeout，成倍放大延迟而不提升成功率。
            if isinstance(exc, TimeoutError):
                break
            if attempt + 1 < attempts:
                logger.info(
                    "结构化输出失败 [%s]，重试 %s/%s：%s: %s",
                    stage,
                    attempt + 1,
                    attempts - 1,
                    type(exc).__name__,
                    exc,
                )
                continue
        else:
            if isinstance(result, schema):
                if attempt:
                    logger.info("结构化输出重试成功 [%s]（第 %s 次尝试）", stage, attempt + 1)
                return result
            last_exc = None  # 未抛错但类型不符，同样值得重试
            if attempt + 1 < attempts:
                logger.info(
                    "结构化输出类型不符 [%s]（%s），重试 %s/%s",
                    stage,
                    type(result).__name__,
                    attempt + 1,
                    attempts - 1,
                )
                continue

    # ── 兜底：清洗工具标记后重新解析 ──────────────────────────────
    if last_raw:
        salvaged = _salvage_from_raw(last_raw, schema, stage)
        if salvaged is not None:
            return salvaged

    if last_exc is not None:
        _log_failure(stage, last_exc)
    else:
        logger.warning("结构化输出类型不符 [%s]，重试 %s 次后仍失败", stage, attempts - 1)
    return None


def _raw_from_validation_error(exc: BaseException) -> str:
    """从 ValidationError 中取回触发失败的原始字符串（模型输出）。

    Pydantic 把原始输入放在每个 error 的 ``input``；批量结构化输出失败时通常
    整条 payload 都在。取其中最长的那个字符串字段 —— 即被撑爆的 ``feedback``。
    """
    if not isinstance(exc, ValidationError):
        return ""
    best = ""
    for e in exc.errors():
        val = e.get("input")
        if isinstance(val, str) and len(val) > len(best):
            best = val
    return best


def _salvage_from_raw[T: BaseModel](raw: str, schema: type[T], stage: str) -> T | None:
    """清洗工具标记后，用原始文本重建结构化对象。

    只在**清洗确实改变了内容**时才尝试；且必须解析成 **dict** 再走 schema 校验
    （与 ``_bind_structured`` 同一条路径），避免把自然语言散文硬塞进字段。

    支持两种实测见过的形态：
    1. 纯 JSON（字段内含 ``<parameter=...>`` 标记）→ 清洗后直接校验；
    2. 裸文本 ``score: 40\\nfeedback: ...`` → 按行首 ``key:`` 拆字段。
    """
    cleaned = _strip_tool_markup(raw)
    if cleaned == raw:
        return None  # 没有标记污染，不属于本兜底能治的情形

    payload = _try_json_dict(cleaned) or _try_kv_dict(cleaned)
    if not payload:
        return None
    try:
        candidate = schema.model_validate(payload)
    except ValidationError:
        return None
    logger.info("结构化输出兜底清洗成功 [%s]：字段 %s", stage, sorted(payload))
    return candidate


def _try_json_dict(text: str) -> dict | None:
    import orjson

    for candidate in (text, _extract_json_object(text)):
        if not candidate:
            continue
        try:
            parsed = orjson.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_json_object(text: str) -> str | None:
    """从文本里截出最外层 ``{...}`` 片段。"""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return text[start : end + 1]


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

    if not fields:
        return None

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


# ③ 字段分类（协议与 `GradingResult` 对齐；由 gate `⑨g` 断言**覆盖 schema 全部字段**）
_KV_SCALAR_FIELDS = frozenset({"score", "feedback", "is_wrong", "error_analysis"})
_KV_LIST_FIELDS = frozenset({"knowledge_points"})
_KV_ALL_FIELDS = _KV_SCALAR_FIELDS | _KV_LIST_FIELDS
# ② 允许**多行续行**的字段（它们本来就是多行自由文本）。
#   ★ 不含 is_wrong / score / knowledge_points —— 避免「续行污染导致语义反转」。
_KV_MULTILINE_FIELDS = frozenset({"feedback", "error_analysis"})
