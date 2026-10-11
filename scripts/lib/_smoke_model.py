"""Agent 行为冒烟的共享模型（`CaseResult`）与启发式正则。

★ 抽出的理由：这些被 session 层与 checks 层共用，且被 `agent_behavior_gate` 直接 import。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    name: str
    reply: str = ""
    tool_payloads: list[dict[str, Any]] = field(default_factory=list)
    hard_fails: list[str] = field(default_factory=list)
    soft_fails: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # ── 多段会话（Memory 评测用）──────────────────────────
    # 每段会话的最终回复（`reply` 仍 = 最后一段的回复，保持向后兼容）
    session_replies: list[str] = field(default_factory=list)
    # 每轮注入的**记忆卡**内容（`load_memory` 的 SystemMessage）。
    # 这是 `recalled` 的**客观证据**：不依赖 judge 猜测。
    memory_cards: list[str] = field(default_factory=list)
    # ── Memory 评测：本次 case 使用的隔离身份（Step 4 硬要求）────
    # ★ 每 case 独立 `user_id` ⇒ 不同 case 的 Store 数据互不污染；
    #   跨会话召回**只能**在同一 case 内发生（Session A 写 → Session B 读）。
    user_id: str = ""
    # ── ★ 批改得分（2026-10-06 补，Step 5 case-validity 用）────────
    # 每次 `grade_student_answer` 调用的得分与所在会话下标：
    #   `[{"session": 0, "score": 52.0}, {"session": 0, "score": 48.0}]`
    # 用途：case 的**前置条件**（如 mem-006「两次高分」、mem-004「低分」）
    #   必须由**实际运行结果**验收，而不是假定模型一定给出预期分数 ——
    #   否则 grading LLM 的随机性会污染 Memory 指标（用户 2026-10-06 裁决）。
    grade_scores: list[dict[str, Any]] = field(default_factory=list)
    # ── ★ Store 开关状态（2026-10-06 补，paired control 用）────────
    # `False` ⇒ 本 case 是 **Store OFF** 对照组（不装 store，B 段不应召回）。
    store_enabled: bool = True
    # ── ★ 逐轮执行日志（2026-10-07 Step 9 补）──────────────────────
    # 每轮一条：`{session, turn, input, reply, tools, grade_scores}`。
    # 为什么必须有：`session_replies` 只到**段**一级，而 `reply` 只留**最后一段** ⇒
    #   「A 段要求 ≥2 次批改，实际只捕获到 1 次」这类 `case_invalid` **无从归因** ——
    #   分不清是「第 2 轮 agent 没调批改工具」还是「调了但没抓到分」（两者的论文含义
    #   完全不同：前者是路由/工具选择问题，后者才是缺陷 A 的批改无分）。
    #   实测依据：Step 9 的 ON 臂三条正样本各只捕获 1 次批改、OFF 臂同三条各 2 次，
    #   而 `score=None` 也会被登记 ⇒ 只能是「第 2 轮没调工具」，但当时**无法证明**，
    #   只能靠这个日志把结论钉死。
    turn_log: list[dict[str, Any]] = field(default_factory=list)
    # ── ★ Store 里实际写入了什么（2026-10-07 Step 9 补）───────────────
    # 每次批改落库的 episode：`{topic, score, knowledge_points, type}`，**在跑后清理之前**读。
    # 为什么必须有：Step 9 实测「A 段两次 0 分低分、前置条件满足，但 B 段 0 张卡」——
    #   唯一的解释是两次批改落在**不同 KP** ⇒ 各 1 hit ⇒ `MEMORY_WEAK_MIN_HITS=2` 永不满足。
    #   可 `grade_scores` 只有分数、工具回文里又不含 KP（`format_grading_for_chat` 只写
    #   评分/结论/错因）⇒ 这个解释**当时无法证明**。把 episode 的 KP 抓下来即可判定。
    episodes: list[dict[str, Any]] = field(default_factory=list)
    # ★ 那次读取**自己抛过错**（2026-10-08 review I3）：此时 `episodes` 为空只说明
    #   「取证通道没读到」，**不能**推断「产品没写入」⇒ 下游的写入证据判据必须闭嘴。
    #   ★ 另注：OFF 臂走的是 `eff_store=None` 分支、压根不读 ⇒ 空属**按构造**，
    #   由 `store_enabled=False` 挡住，不需要这个标志。
    episodes_read_failed: bool = False


_EMPTY_ACK_RE = re.compile(r"未检索到|未找到|没有找到|知识库.{0,6}(未|没有|无)|未覆盖|检索不到")

_FAB_PAGE_RE = re.compile(r"第\s*\d+\s*页|P\s*\d{1,4}|《[^》]{1,20}》\s*第\s*\d+\s*章")

_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer|correct_answer", re.I)

_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】|正确答案|标准答案")

_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")

_SOURCE_RE = re.compile(r"来源[:：]\s*([^\n]+)")

_SELF_SCORE_RE = re.compile(r"(?:得分|评分|得分是|我给)\s*[:：]?\s*\d+\s*(?:/\s*\d+)?\s*分?")


# 批改工具输出是对话体文本（见 `grading_core.format_grading_for_chat`）⇒ 正则提分。
_GRADE_SCORE_RE = re.compile(r"评分\s*[:：]\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+))?")

_GRADE_FULL_SCORE = 100.0
