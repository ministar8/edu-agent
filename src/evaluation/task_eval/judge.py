"""LLM-as-judge + 人工校准（§2.B.2 / 决策 #4）。

口径（用户拍板）：
- **B 方案**：LLM 全量评分 + **20% 人工抽检**；**正式启用前必须先做校准**。
- 校准：~30 条同时拿 LLM 分与人工分，比 `exact` / `within_1` / `MAE` / `Spearman`，
  并检查 **0/1/5 边界**是否有系统性偏差。
- 达标才允许 LLM 进入批量评分；抽检发现偏差 → 人工仲裁 + 重校准。

★ 阈值（`CALIBRATION_THRESHOLDS`）是「预先约定标准」的落点。数值来自提案，
  若与你的最终口径不符，改这一处即可 —— 不要在别处散落阈值。
★ judge 用**比生成模型更强**的模型（`settings.ragas_judge_model`），避免自评偏差。
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from core.settings import settings
from evaluation.task_eval.cases import TaskCase
from evaluation.task_eval.metrics import FAILURE_REASONS, pick_primary_failure

logger = logging.getLogger(__name__)

# 「预先约定标准」——校准通过的四个门槛（提案值，待你最终确认）
CALIBRATION_THRESHOLDS: dict[str, float] = {
    "exact": 0.60,  # 完全同分率
    "within_1": 0.90,  # ±1 分一致率
    "mae_max": 0.50,  # MAE 上限
    "spearman_min": 0.70,  # 秩相关下限
}

JUDGE_TIMEOUT = 120.0


class JudgeOutput(BaseModel):
    """judge 的结构化输出。`final_quality` 为 task-aware 0–5 总分。"""

    final_quality: int = Field(ge=0, le=5, description="task-aware rubric 0–5 总分")
    failure_reason: list[str] = Field(default_factory=list, description="完整故障链（可多个）")
    rationale: str = Field(default="", description="一句话判据说明")
    # memory 三维（仅多轮 case 需要；单轮留 None）
    memory_retrieved: bool | None = None
    memory_used: bool | None = None
    memory_correct: bool | None = None
    # ── Generate 三项子判据（§3.1 五项完整交付率的组成部分）──────────
    #    ★ 为什么交给 judge：这三项都要读题目内容才能判，机械规则覆盖不了。
    #      仅 Generate 任务需要；其他任务留 None。
    completeness_ok: bool | None = Field(
        default=None, description="Generate：题干+选项/要求+标准答案+解析 四要素是否齐全"
    )
    answerable: bool | None = Field(
        default=None, description="Generate：题目本身是否**可作答**（信息充分、无歧义、无自相矛盾）"
    )
    answer_correct: bool | None = Field(
        default=None, description="Generate：给出的标准答案在知识点与结论上**是否正确**"
    )


# ── task-aware rubric（§2.B.2，统一 0–5，判据按任务）─────────
_RUBRIC_QA_VERIFY = """评分（0–5）：
5 = 正确 + 切题 + 引用证据 + 结构完整
4 = 基本正确，小瑕疵
3 = 关键点缺 或 部分错
2 = 半数错 或 严重遗漏
1 = 答非所问 / 事实错
0 = 空 / 拒答 / 幻觉 / hard_fail"""

_RUBRIC_GENERATE = """评分（0–5）：
5 = 题目正确、考点明确、答案可判定、解析完整、符合题型
4 = 基本完整，轻微瑕疵
3 = 能用，但明显缺项
2 = 题目/答案有较严重问题
1 = 题目本身不可用
0 = 拒答 / 幻觉 / 崩溃

**另外请逐项判定以下三项子判据**（这是「五项完整交付率」的组成部分，务必都填）：
- `completeness_ok`：**题干 + 选项/要求 + 标准答案 + 解析** 四要素是否**齐全**
  （简答/计算题的「要求」= 明确的小问，如 (1)(2) 或「请写出/请说明」）
- `answerable`：题目本身**是否可作答** —— 信息是否充分、有无歧义、有无自相矛盾、
  有无缺失条件导致无法求解
- `answer_correct`：给出的**标准答案是否正确**（知识点、结论、计算过程）
"""

_RUBRIC_GRADE = """评分（0–5）：
5 = 结论正确 + 得分合理(±10) + 扣分点正确 + 反馈有帮助
4 = 结论正确，细微偏差
3 = 结论对，但得分/扣分有明显偏差
2 = 结论错，方向对
1 = 结论判反
0 = 空 / 崩溃"""

_RUBRIC_MEMORY = """这是**多轮记忆**任务，请按「长期记忆是否被正确使用」评分（0–5），
**不要**用检索/知识问答的口径（记忆类提问本就不该命中知识库，检索为空是正常的）：

5 = 正确回忆并使用了上一轮/历史中的个人信息或偏好，且回答直接受益于它
4 = 用到了记忆，但细节有小偏差
3 = 部分用对（如只用到一项），或记忆存在但未充分使用
2 = 提到记忆但用错，或该用却只泛泛作答
1 = 完全没用记忆，回答了通用内容
0 = 空 / 拒绝 / 幻觉（编造未出现过的用户信息）

★ **不要**再去判定 recalled / used / correct 三项 ——
  这三项已改为**机械判定**（从 `load_memory` 注入的记忆卡直接读取，
  见 `memory_scorer.py`），judge 的对应判断**不会被采纳**。
  你的职责只剩上面这个 0–5 质量分与 `failure_reason`。
"""

_RUBRICS: dict[str, str] = {
    "qa": _RUBRIC_QA_VERIFY,
    "verify": _RUBRIC_QA_VERIFY,
    "generate": _RUBRIC_GENERATE,
    "grade": _RUBRIC_GRADE,
    "memory": _RUBRIC_MEMORY,
}

_SYSTEM = (
    "你是 408 考研教学系统的效果评审员。只依据给定的【任务】、【gold】与【系统输出】"
    "打分，不要引入外部知识去补全系统没说的事。\n"
    "failure_reason 只能从这个枚举里选（可多选）：{reasons}\n"
    "若输出没有问题，failure_reason 填空列表。\n\n{rubric}"
)


def rubric_for(task: str) -> str:
    """取该 task 的 0–5 rubric 文本（供**人工标注表**附判据，保证人机同一把尺子）。"""
    return _RUBRICS.get(task, _RUBRIC_QA_VERIFY)


def build_judge_prompt(case: TaskCase, reply: str, hard_fails: list[str]) -> str:
    """拼 judge 提示词：任务 + gold + 系统输出 + 硬失败。"""
    gold = case.gold
    gold_lines: list[str] = []
    for name in (
        "gold_points",
        "expected_kp",
        "expected_difficulty",
        "gold_answer",
        "expected_question_ids",
        "human_score",
        "reference",
    ):
        value = getattr(gold, name, None)
        if value not in (None, "", []):
            gold_lines.append(f"- {name}: {value}")
    gold_text = "\n".join(gold_lines) or "（无 gold，按通用正确性判断）"
    turns_text = ""
    if len(case.all_turns) > 1:
        turns_text = (
            "【多轮输入】\n"
            + "\n".join(f"{i}. {t}" for i, t in enumerate(case.all_turns, 1))
            + "\n"
        )
    return (
        f"【任务】{case.task}（task_mode={case.task_mode or 'auto'}）\n"
        f"【用户输入】{case.query}\n"
        f"{turns_text}"
        f"【gold】\n{gold_text}\n"
        f"【硬失败】{hard_fails or '无'}\n"
        f"【系统输出】\n{reply or '（空）'}\n"
    )


def _coerce_judge_output(raw: object) -> JudgeOutput | None:
    """宽容地把模型输出规整成 `JudgeOutput`。

    ★ 为什么需要（2026-10-05 实测）：`qwen3.8-27b` 经 `with_structured_output` 返回的是
      **JSON 数组** `[{...}]` 而非对象，pydantic 直接报
      `Input should be an object [type=model_type, input_type=list]` —— judge 全数作废。
      网关/模型对「结构化输出」的实现不一致，故这里统一兜底：
      数组取首元素、字符串剥围栏后 JSON 解析、dict 直接校验。
    """
    if isinstance(raw, JudgeOutput):
        return raw
    if isinstance(raw, list):
        raw = next((x for x in raw if isinstance(x, (dict, str))), None)
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(raw, list):
            raw = next((x for x in raw if isinstance(x, dict)), None)
    if not isinstance(raw, dict):
        return None
    # 模型可能用别名（score/quality）——只做最小映射，不猜复杂结构
    if "final_quality" not in raw:
        for alias in ("quality", "score", "final_score"):
            if alias in raw:
                raw["final_quality"] = raw[alias]
                break
    try:
        return JudgeOutput.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("judge 输出无法解析为 JudgeOutput: %s | raw=%s", e, str(raw)[:200])
        return None


async def _invoke_judge(llm, messages: list[dict[str, str]]) -> JudgeOutput | None:
    """优先结构化输出；失败则退回「纯文本 + 宽容解析」。两种都失败 → None。"""
    try:
        structured = llm.with_structured_output(JudgeOutput)
        out = await asyncio.wait_for(structured.ainvoke(messages), timeout=JUDGE_TIMEOUT)
        coerced = _coerce_judge_output(out)
        if coerced is not None:
            return coerced
    except Exception as e:  # noqa: BLE001
        logger.debug("结构化 judge 输出失败，转纯文本兜底: %s", e)

    try:
        ask = [
            *messages,
            {"role": "user", "content": "只输出一个 JSON 对象（不要数组、不要围栏）。"},
        ]
        raw = await asyncio.wait_for(llm.ainvoke(ask), timeout=JUDGE_TIMEOUT)
        return _coerce_judge_output(getattr(raw, "content", raw))
    except Exception as e:  # noqa: BLE001
        logger.warning("judge 纯文本兜底也失败: %s: %s", type(e).__name__, e)
        return None


async def judge_case(case: TaskCase, reply: str, hard_fails: list[str]) -> JudgeOutput | None:
    """对一条 case 调 LLM judge。失败（超时/解析错）返回 None，**不抛出**。"""
    from core.llm import get_llm

    system = _SYSTEM.format(
        reasons=", ".join(FAILURE_REASONS), rubric=_RUBRICS.get(case.task, _RUBRIC_QA_VERIFY)
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_judge_prompt(case, reply, hard_fails)},
    ]
    try:
        llm = get_llm(
            streaming=False,
            temperature=0.0,
            model_ref=settings.ragas_judge_model,
            disable_thinking=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("judge 初始化失败 case=%s: %s", case.case_id, e)
        return None
    out = await _invoke_judge(llm, messages)
    if out is None:
        logger.warning("judge 失败 case=%s（结构化与兜底均未产出可用结果）", case.case_id)
    return out


# Memory 不适用的检索层 failure_reason —— judge 常把它们套到 memory 上（实测 6/6 被标
# `retrieval_miss`），但 memory 的 query 本就不是知识查询，检索返空属预期。
# 归因口径错误会直接误导 Phase 1 的优化方向，故在此**过滤掉**。
_RETRIEVAL_LAYER_REASONS = frozenset({"retrieval_miss", "retrieval_dropped", "evidence_pollution"})


def retrieval_layer_gate_open(
    retrieval_status: object, pack_nonempty: object, task: object = ""
) -> bool:
    """检索层归因的 **tier-0 门**（`EVIDENCE_CHAIN.md` §4.3「Verify 归因」行）。

    为什么要有这道门（实测，非措辞）：`phase1_final_gate_20261008.jsonl` 的 15 条 verify
    `retrieval_status` **全是 `ok`**、`pack_nonempty` **全是 True**、`evidence_count` 1–5，
    而 `primary_failure` 仍被顶成 `retrieval_miss`×15 —— 机械路径（本函数原来那行
    `not pack_nonempty`）根本没触发，那 15 条只能是 **judge 的意见**，再被
    `metrics._PRIMARY_PRIORITY` 排到第 3 位当根因。两个 tier-0 见证都反对的归因
    不配当「主要失败原因」。

    三行规则（表的逐字落地）：

    | tier-0 证据 | 检索层原因 |
    |---|---|
    | `retrieval_status == "error"` | ★ 禁（那是基础设施故障，由 `tool_error` 表达）|
    | `retrieval_status == "empty"` ∧ `pack_nonempty is False` | ★ 允许（唯一开门的组合）|
    | `retrieval_status == "ok"` ∨ `pack_nonempty is True` | ★ 禁（包里有东西，谈什么没查到）|

    ★ `retrieval_status == ""`（老归档没写这个键 / 未测量）⇒ **关门**：
      「没记录」不能反推成「检索没查到」。这不是为了让数字好看 —— 老归档的归因分布
      本就属旧口径（见 Task 8 报告 D-4），不许拿当前配置猜当时。
    ★ `task == "memory"` 时同样关门：memory 的 query 不是知识查询，返空属预期
      （与既有 `_RETRIEVAL_LAYER_REASONS` 过滤同口径，此处只是把它并进同一道门）。
    """
    if str(task) == "memory":
        return False
    if str(retrieval_status) != "empty":
        return False
    return pack_nonempty is False


def split_retrieval_layer_reasons(
    reasons: Sequence[str], *, retrieval_status: object, pack_nonempty: object, task: object = ""
) -> tuple[list[str], list[str]]:
    """把一组 reason 切成「可进 `failure_reason`」与「必须隔离」两份。

    ★ 隔离的是**没有 tier-0 证据支撑**的检索层原因；其余 reason 原样通过。
    """
    allowed: list[str] = []
    quarantined: list[str] = []
    open_gate = retrieval_layer_gate_open(retrieval_status, pack_nonempty, task)
    for r in reasons:
        if r in _RETRIEVAL_LAYER_REASONS and not open_gate:
            quarantined.append(r)
        else:
            allowed.append(r)
    return allowed, quarantined


def _sync_generate_correctness(record) -> None:
    """judge 写入 `final_quality` 后，**同步刷新** Generate 的「内容正确率」。

    ★ 「谁写 `final_quality`，谁负责刷新依赖它的派生指标」这条归属规则保留（2026-10-06 修：
      runner 里算时 judge 还没跑 ⇒ 15 条全 N/A 的教训），只是公式来源从本地 `fq>=4`
      副本换成 `predicates.registry` 的唯一定义（Task 4：三份本地公式删净，rejudge 与
      新跑同源）。无 gold ⇒ `missing_premise`（落盘 None + item_reasons 记原因）。
    """
    if getattr(record, "task", "") != "generate":
        return
    from evaluation.task_eval.predicates import common as pc
    from evaluation.task_eval.predicates import registry

    v = registry.get("gen_correctness").fn(record.to_dict())
    record.gen_correctness = pc.to_record_value(v)
    record.item_reasons["gen_correctness"] = "" if v in ("pass", "fail") else v


def _quarantine_judge_memory(output: JudgeOutput) -> None:
    """**护栏**：judge 对 Memory 三维的判断一律**不采纳**（2026-10-06 定稿）。

    为什么必须拦
    ------------
    Memory 三维的正确来源是**机械事实**：`recalled` 读 harness 从 `load_memory`
    捕获的记忆卡（`CaseResult.memory_cards`，见 `memory_scorer.py`），
    不经任何 LLM。

    而 judge 的 rubric 曾要求它顺带判定三维 —— 实测两处危害：

    1. **主观误判**：`recalled` 本是客观事实（卡里有没有），LLM 只能凭回复猜；
    2. **三态不一致**：`mem-004` 的 `memory_correct` 被判成 `None`，
       而 `memory_correct_use` 要求三者全非 None ⇒ 主指标凭空变 N/A。

    ★ 处理方式：judge 的判定**保留在 `judge_memory_*` 前缀的独立字段**里作为诊断
      （便于「机械 vs 主观」对照，量化 judge 偏了多少），但**主指标字段
      `memory_retrieved` / `memory_used` / `memory_correct` 一律不由 judge 写**。
      它们只由 `memory_scorer.judge_memory_mechanically()` 填。
    """
    # 诊断留档：字段名带 `judge_` 前缀，明确非指标来源
    setattr(output, "_judge_memory_retrieved", output.memory_retrieved)
    setattr(output, "_judge_memory_used", output.memory_used)
    setattr(output, "_judge_memory_correct", output.memory_correct)


def _judge_memory_diagnostics(output: JudgeOutput) -> dict[str, Any]:
    """把 judge 的 Memory 三维判断转成**诊断** dict（不进指标）。"""
    return {
        "judge_memory_retrieved": output.memory_retrieved,
        "judge_memory_used": output.memory_used,
        "judge_memory_correct": output.memory_correct,
    }


def apply_judge(record, output: JudgeOutput | None) -> None:
    """把 judge 结果并回 record：质量分 + 生成侧 failure_reason。

    ★ Memory 三维**不在此写入** —— 由 `memory_scorer` 机械判定（见
      `_quarantine_judge_memory`）。此处仅把 judge 的对应判断留作诊断字段。
    """
    if output is None:
        return
    record.final_quality = float(output.final_quality)
    extra = [r for r in output.failure_reason if r in FAILURE_REASONS]
    # ★ tier-0 门：judge 单独给的检索层原因**不进** `failure_reason`，落 `judge_failure_reasons`
    #   留作「机械 vs 主观」对照（与 `_quarantine_judge_memory` 同一套已验证的隔离模式）。
    allowed, quarantined = split_retrieval_layer_reasons(
        extra,
        retrieval_status=getattr(record, "retrieval_status", ""),
        pack_nonempty=getattr(record, "pack_nonempty", None),
        task=getattr(record, "task", ""),
    )
    record.judge_failure_reasons = sorted(set(quarantined))
    merged = list(record.failure_reason) + allowed
    record.failure_reason = sorted(set(merged))
    record.primary_failure = pick_primary_failure(record.failure_reason)
    if getattr(record, "task", "") == "memory":
        # ★ 护栏：不写 memory_retrieved / memory_used / memory_correct
        _quarantine_judge_memory(output)
        for k, v in _judge_memory_diagnostics(output).items():
            setattr(record, k, v)
    record.judge = settings.ragas_judge_model
    _sync_generate_correctness(record)


# ── 只重判、不重跑（换 judge 时的省钱路径）─────────────────
#
# 为什么需要：judge 换了但 agent 没换时，**已归档的 reply 仍然有效** ——
# 重跑会重算 496 次调用（≈55–67万 token），而重判只需 66 次（≈7–9万）。
# 且重判用的是**同一批 reply**，是「同输入不同 judge」的**配对比较**，
# 比重新生成更适合隔离 judge 的影响。


# ★ 这两个 reason 由 **runner / 标注环节**写入，judge 从不产出，也不依赖本轮生成质量：
#   `case_invalid` = A 段前置条件没成立（`runner.run_case` 的 memory 分支里 validity 为 False 那一支），
#   `memory_miss` = gold 未标注/非法（`runner._apply_memory_judgement` 返回的 extra，是「请人工补标」的记号）。
#   ★ 引用**符号**而不是行号：行号会随每次改动过期（这里就长期写着 `runner.py:505` / `:382`，
#     实际两处早已搬家），而符号名变了 IDE/重命名会直接带我走。
#   重判把旧 reasons 整个清掉重算，若不显式保留它们，这二类记录会被
#   **洗成 `primary_failure=none`（看起来像满分通过）**。
#   实测：`phase1_memory_step5_store_off.jsonl` 里 4 条 `case_invalid` 的
#   `failure_reason` 恰好只有 `["case_invalid"]` ⇒ 重判后变 `[]`。
_KEEP_ON_REJUDGE: frozenset[str] = frozenset({"case_invalid", "memory_miss"})


def mechanical_reasons_from_record(rec: dict) -> list[str]:
    """从归档 record 的字段重算**机械判据**（与 `runner.mechanical_failures` 同口径）。

    重判时必须把上一轮 judge 给的 reasons 清掉、只保留机械判据，
    否则新旧 judge 的 reasons 会累积混在一起。

    ★ 例外：`_KEEP_ON_REJUDGE` 两项不是 judge 的意见，而是「样本本身不可用」的归因，
      清掉它们会把「样本无效」误报成「产品通过」，故原样保留。
      `case_invalid` 另按 `validity_valid` 兜底重建 —— 若上一轮已被误清，
      该字段仍是有权威性的落盘证据，能把它恢复回来。
    """
    reasons: list[str] = []
    hard = " ".join(rec.get("hard_fails") or [])
    if "invoke 抛错" in hard or "工具" in hard or rec.get("retrieval_status") == "error":
        reasons.append("tool_error")
    # ★ tier-0 门（Task 8 Step 5）：机械路径也走同一道门 —— 旧实现只看 `not pack_nonempty`，
    #   而 `retrieval_status == "error"` 时 `pack_nonempty` **同样是 False**（都来自 `probe.ok`），
    #   于是「路由坏了」会同时产出 `tool_error` **和** `retrieval_miss`，后者再被
    #   `_PRIMARY_PRIORITY` 顶成根因 ⇒ 基础设施故障被记成产品检索能力缺失。
    if retrieval_layer_gate_open(
        rec.get("retrieval_status"), rec.get("pack_nonempty"), rec.get("task")
    ):
        reasons.append("retrieval_miss")
    if not (rec.get("reply") or "").strip():
        reasons.append("generation_incomplete")

    archived = set(rec.get("failure_reason") or [])
    reasons.extend(sorted(_KEEP_ON_REJUDGE & archived))
    if rec.get("validity_valid") is False and "case_invalid" not in reasons:
        reasons.append("case_invalid")
    return sorted(set(reasons))


def apply_judge_to_dict(rec: dict, output: JudgeOutput | None, *, judge_model: str) -> None:
    """把 judge 结果写回**已归档的 dict record**（就地修改）。

    ★ 与 `apply_judge` 同护栏：Memory 三维**不写**，只留 `judge_memory_*` 诊断字段。
    """
    if output is None:
        return
    rec["final_quality"] = float(output.final_quality)
    extra = [r for r in output.failure_reason if r in FAILURE_REASONS]
    # ★ tier-0 门 + 隔离（与 `apply_judge` 同源，一份规则两处不许分叉）：
    #   judge 单独给的检索层原因落 `judge_failure_reasons`，**不参与** `pick_primary_failure`。
    allowed, quarantined = split_retrieval_layer_reasons(
        extra,
        retrieval_status=rec.get("retrieval_status", ""),
        pack_nonempty=rec.get("pack_nonempty"),
        task=rec.get("task", ""),
    )
    rec["judge_failure_reasons"] = sorted(set(quarantined))
    merged = sorted(set(mechanical_reasons_from_record(rec)) | set(allowed))
    rec["failure_reason"] = merged
    rec["primary_failure"] = pick_primary_failure(merged)
    if rec.get("task") == "memory":
        # ★ 护栏：不写 memory_retrieved / memory_used / memory_correct
        _quarantine_judge_memory(output)
        rec.update(_judge_memory_diagnostics(output))
    rec["judge"] = judge_model
    if rec.get("task") == "generate":
        # ★ Task 4：第三份 `fq>=4` 本地公式删除，与 `_sync_generate_correctness` 同源
        #   到 registry —— 不切的话 rejudge 与新跑会分叉成两套口径（#36 的旧病）。
        #   切换后 rejudge 产物里 `gen_correctness` 变 missing_premise（无 gold）——
        #   语义修正的预期结果，不是回归；`judge_failure_reasons` 等诊断字段不动。
        from evaluation.task_eval.predicates import common as pc
        from evaluation.task_eval.predicates import registry

        v = registry.get("gen_correctness").fn(rec)
        rec["gen_correctness"] = pc.to_record_value(v)
        rec.setdefault("item_reasons", {})["gen_correctness"] = "" if v in ("pass", "fail") else v


# ── 校准 ──────────────────────────────────────────────────


@dataclass
class CalibrationReport:
    n: int = 0
    exact: float | None = None
    within_1: float | None = None
    mae: float | None = None
    spearman: float | None = None
    boundary_bias: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    failed_on: list[str] = field(default_factory=list)
    # ★ D6（2026-10-07，登记为 §20.5 #19）：**秩相关的信息量必须自己说出来**。
    #   实测 `calibration_30.jsonl` 的 `human_score` 分布 = `{5: 28, 0: 1, 2: 1}` ⇒
    #   众数占 93.3%，`spearman` 的判别力全在**那 2 行**上（把任一条改成 5 就掉到 ~0.5 FAIL；
    #   把那两行的 judge 分改成 0 却**仍然 PASS**，因为秩相关只看排序不看量级）。
    #   ⇒ 「PASS」可以是真的，但引用它当「judge 与人工秩相关良好」就是过度声称。
    #   ★ 这里**只加露出，不动判定**：阈值（`CALIBRATION_THRESHOLDS`）是「预先约定标准」的落点，
    #     人工分是真实标注 —— 两者都不许为了好看去改（后者等于伪造数据）。
    human_mode: float | None = None
    informative_n: int = 0
    informative_share: float | None = None
    rank_degenerate: bool = False


def _human_dispersion(human: list[float]) -> tuple[float | None, int, float | None]:
    """返回（众数、非众数行数、非众数占比）。占比为 None ⇒ 无可比对样本。"""
    if not human:
        return None, 0, None
    counts: dict[float, int] = {}
    for b in human:
        counts[b] = counts.get(b, 0) + 1
    mode = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    informative = sum(1 for b in human if b != mode)
    return mode, informative, round(informative / len(human), 4)


# 阈值：非众数样本不足 20% ⇒ 秩相关由极少数行决定，必须显式标出（不是判失败，是禁止过度引用）
# ★ 用公开名：`cli` 与护栏都要引用它。原先是私有名，调用方只能跨模块取 `_xxx`（review M5）
#   —— 那是耦合，不是复用。
INFORMATIVE_SHARE_MIN = 0.20


def calibrate(llm_scores: list[float], human_scores: list[float]) -> CalibrationReport:
    """LLM 分 vs 人工分的一致性报告（§决策 #4）。"""
    pairs = [(float(a), float(b)) for a, b in zip(llm_scores, human_scores, strict=False)]
    if not pairs:
        return CalibrationReport()
    n = len(pairs)
    exact = sum(1 for a, b in pairs if a == b) / n
    within_1 = sum(1 for a, b in pairs if abs(a - b) <= 1) / n
    mae = sum(abs(a - b) for a, b in pairs) / n
    rho = _spearman([a for a, _ in pairs], [b for _, b in pairs])
    mode, inf_n, inf_share = _human_dispersion([b for _, b in pairs])
    report = CalibrationReport(
        n=n,
        exact=round(exact, 4),
        within_1=round(within_1, 4),
        mae=round(mae, 4),
        spearman=round(rho, 4) if rho is not None else None,
        boundary_bias=_boundary_bias(pairs),
        human_mode=mode,
        informative_n=inf_n,
        informative_share=inf_share,
        rank_degenerate=(inf_share is not None and inf_share < INFORMATIVE_SHARE_MIN),
    )
    checks = {
        "exact": exact >= CALIBRATION_THRESHOLDS["exact"],
        "within_1": within_1 >= CALIBRATION_THRESHOLDS["within_1"],
        "mae": mae <= CALIBRATION_THRESHOLDS["mae_max"],
        "spearman": (rho is not None) and (rho >= CALIBRATION_THRESHOLDS["spearman_min"]),
    }
    report.failed_on = [k for k, ok in checks.items() if not ok]
    report.passed = not report.failed_on
    return report


def _boundary_bias(pairs: list[tuple[float, float]]) -> dict[str, float]:
    """0/1/5 三个边界档上的「LLM − 人工」平均偏差（正 = judge 偏高）。"""
    out: dict[str, float] = {}
    for level in (0.0, 1.0, 5.0):
        sel = [a - b for a, b in pairs if b == level]
        if sel:
            out[str(int(level))] = round(sum(sel) / len(sel), 3)
    return out


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman 秩相关（不引入 scipy：秩相关 = 秩上的 Pearson）。常数序列 → None。"""
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _ranks(values: list[float]) -> list[float]:
    """平均秩（并列取平均）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks
