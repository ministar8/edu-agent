"""Gold Sanity Check：进 0B **之前**验证 gold 本身合法（不是评价效果）。

为什么必须有
------------
0A 实测暴露：`kp_hit` 恒为 0 的根因是 **gold 与检索侧的命名空间错配**，不是检索失败。
即「evaluator 自己的 fail」会被读成「系统的 fail」。本检查把这类问题挡在 0B 之前。

两级判定（**必须分开**，否则会把「还没标」误报成「标错了」）
--------------------------------------------------------
- `ERROR`  ：gold **已填但非法**（如 `expected_kp` 不是合法考点 ID、
             `expected_question_ids` 指向不存在的题、`expected_difficulty=9`）。
             ⇒ **阻止进入 0B**（exit 1）。
- `PENDING`：draft 阶段**尚未标注**（如 `gold_answer` 为空、`human_score` 为空）。
             ⇒ 只提示，**不算失败**（Phase 0 允许 gold 处于 draft）。

用法::

    PYTHONPATH=src uv run python -m evaluation.task_eval sanity
    PYTHONPATH=src uv run python -m evaluation.task_eval sanity --task grade
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from evaluation.task_eval.assets import (
    is_valid_kp_id,
    load_kp_index,
    parse_exam_items,
)
from evaluation.task_eval.cases import GOLD_FIELDS, TASKS, TaskCase

logger = logging.getLogger(__name__)

ERROR = "ERROR"
PENDING = "PENDING"

_VALID_DIFFICULTY_TEXT = {"basic", "easy", "medium", "mid", "hard", "difficult"}


@dataclass
class SanityIssue:
    case_id: str
    task: str
    level: str
    field_name: str
    message: str


@dataclass
class SanityReport:
    n_cases: int = 0
    issues: list[SanityIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[SanityIssue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def pendings(self) -> list[SanityIssue]:
        return [i for i in self.issues if i.level == PENDING]

    @property
    def ok(self) -> bool:
        return not self.errors


# ── 单项检查 ──────────────────────────────────────────────


def _check_kp(case: TaskCase, kp_index: dict, out: list[SanityIssue]) -> None:
    kps = case.gold.expected_kp
    if not kps:
        out.append(
            SanityIssue(case.case_id, case.task, PENDING, "expected_kp", "未标注 expected_kp")
        )
        return
    for kp in kps:
        if not is_valid_kp_id(kp, kp_index):
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "expected_kp",
                    f"{kp!r} 不是合法考点 ID（也未作为祖先存在）—— 会造成 kp_hit 恒 0 的口径错配",
                )
            )


def _check_verify(case: TaskCase, question_ids: set[str], out: list[SanityIssue]) -> None:
    ids = case.gold.expected_question_ids
    if not ids:
        out.append(SanityIssue(case.case_id, case.task, PENDING, "expected_question_ids", "未标注"))
        return
    missing = [q for q in ids if q not in question_ids]
    if missing:
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "expected_question_ids",
                f"指向不存在的真题：{missing[:5]}（共 {len(missing)} 个）",
            )
        )


def _check_grade(case: TaskCase, stem_to_answer: dict[str, str], out: list[SanityIssue]) -> None:
    stem = case.gold.question_stem
    if not stem:
        out.append(
            SanityIssue(case.case_id, case.task, ERROR, "question_stem", "缺失（Grade 必须题干）")
        )
    else:
        key = _norm_stem(stem)
        if key not in stem_to_answer:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "question_stem",
                    "在真题库里找不到对应题目 → 无法核对 answer_key",
                )
            )
        elif not stem_to_answer[key]:
            out.append(
                SanityIssue(case.case_id, case.task, ERROR, "answer_key", "对应真题缺 answer_key")
            )
    if case.gold.human_score is None:
        out.append(
            SanityIssue(case.case_id, case.task, PENDING, "human_score", "未标注（需先立 rubric）")
        )
    elif not 0 <= case.gold.human_score <= 100:
        out.append(
            SanityIssue(
                case.case_id, case.task, ERROR, "human_score", f"{case.gold.human_score} 不在 0–100"
            )
        )
    if case.gold.full_marks != 100.0:
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "full_marks",
                f"必须为 100（批改输出 0–100），实为 {case.gold.full_marks}",
            )
        )


def _check_generate(case: TaskCase, out: list[SanityIssue]) -> None:
    """Generate 的 gold 检查（§3.1 v1.0 **冻结口径 B**，2026-10-06 用户裁决）。

    ★ 口径变更：**`expected_difficulty` 与 `gold_answer` 不再算「待标注（PENDING）」**。
      理由（用户拍板）：
        - `expected_difficulty` 无可靠 gold 来源（黄金集无难度字段、query 0/32 提及难度）
          ⇒ 记 **N/A**，`difficulty_match_pass` **不适用、不扣分**；❌ 禁止编默认难度。
        - `gold_answer` **不得**拿黄金集示例题答案冒充生成题的 gold
          ⇒ 该字段**不适用**，`correctness_pass` 改用校准后的 judge 判断。
      ⇒ 二者是**有意不适用**，不是「还没标」。若仍报 PENDING，会让 sanity 永远不 PASS。
    """
    diff = case.gold.expected_difficulty
    # 仅在**显式提供了难度**时校验其合法性（提供了却不在 1–5 档 → 真 ERROR）
    if diff is not None:
        valid = False
        if isinstance(diff, (int, float)) and not isinstance(diff, bool):
            valid = 1 <= int(diff) <= 5
        else:
            valid = str(diff).strip().lower() in _VALID_DIFFICULTY_TEXT
        if not valid:
            out.append(
                SanityIssue(
                    case.case_id, case.task, ERROR, "expected_difficulty", f"{diff!r} 不属 1–5 档"
                )
            )
    # expected_difficulty / gold_answer 缺失 → 按冻结口径属**不适用**，不报 PENDING


def _check_field_ownership(case: TaskCase, out: list[SanityIssue]) -> None:
    """gold 里出现**不属于该 task** 的字段 → 标错位置（ERROR，会导致指标读不到）。"""
    allowed = set(GOLD_FIELDS.get(case.task, ()))
    # `full_marks`（有默认值的评分参数）与 `gold_source_ref`（gold 的**出处元数据**，
    # 每个 task 都可能需要）都不属于「该 task 专属的 gold 字段」这一维度 ⇒ 不参与归属扫描。
    ignored = ("full_marks", "gold_source_ref")
    present = {
        k for k, v in case.gold.__dict__.items() if k not in ignored and v not in (None, [], "")
    }
    stray = present - allowed
    if stray:
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "gold",
                f"出现不属于 task={case.task} 的字段 {sorted(stray)}（允许 {sorted(allowed)}）",
            )
        )


def _check_gold_source_ref(case: TaskCase, out: list[SanityIssue]) -> None:
    """gold 里有值，就必须能指回外部出处（EVIDENCE_CHAIN.md §4.2 盲标规程第 2 条）。

    只检查**有值**的字段：无 gold 属 `missing_premise`，不是标注缺陷 ⇒ 不报 ERROR。
    """
    refs = case.gold.gold_source_ref or {}
    for field_name in ("gold_answer", "expected_difficulty", "human_score"):
        if getattr(case.gold, field_name, None) is not None and not refs.get(field_name):
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    field_name,
                    "有值但无 gold_source_ref（无出处的 gold 视为未填）",
                )
            )


def _check_memory(case: TaskCase, kp_index: dict, out: list[SanityIssue]) -> None:
    """Memory 的 gold 检查（v1 契约，2026-10-06 定稿）。

    为什么必须 ERROR 而非 PENDING
    ----------------------------
    Memory 三项主指标已改为**机械判定**（`memory_scorer.py`，judge 不参与）。
    机械判定需要 `expected_memory` 与 `expected_answer_property` 里的**每一个字段**：
    缺 `values` ⇒ `used`/`recalled` 无从计算；缺 `should_be_recalled` ⇒ 分不清正负样本；
    缺 `forbidden_values` ⇒ `correct` 退化成 `used` 的副本。

    ⇒ 缺任一字段都让该项判定**退回主观猜测** —— 这正是本轮要根除的问题。
      故标 **ERROR**（不是 PENDING）：宁可不测，不可假测。

    ★ `values` 必须是 **canonical KP 名**：与 `expected_kp` 同源校验。
      理由：避免「LLM 输出 `AVL树旋转`、gold 写 `AVL树`」这类字符串漂移，
      使 `in` 判定产生**系统性假阴性**（与 kp_hit 恒 0 是同一类口径错配）。
    """
    from evaluation.task_eval.cases import MEMORY_TYPES

    em = case.gold.expected_memory
    eap = case.gold.expected_answer_property

    # —— expected_memory ——
    if em is None:
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "expected_memory",
                "缺失 —— Memory 三项无法机械判定（禁止退化为 judge 主观判定）",
            )
        )
    else:
        if em.type not in MEMORY_TYPES:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "expected_memory.type",
                    f"{em.type!r} 不在允许集合 {sorted(MEMORY_TYPES)}（产品当前仅支持 weak_topics）",
                )
            )
        if not em.values:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "expected_memory.values",
                    "空或缺失 —— used / recalled 无从计算",
                )
            )
        else:
            # ★ 这里必须校验 **name（规范名）**，不是 **ID**（2026-10-06 修）：
            #   `kp_index` 的 key 是 ID（如 `ds.graph`），value.name 才是给人看的规范名
            #   （如 `图`）。而 Memory 的 `values` 要匹配的是**记忆卡正文/回复里的文本**
            #   —— 那里面出现的是「图」，不是「ds.graph」。
            #   用 `is_valid_kp_id`（校验 ID）会把合法名全判非法（本 Gate ⑤c 实测抓到）。
            canonical_names = {str(v.get("name") or "") for v in kp_index.values()}
            for v in em.values:
                if v not in canonical_names:
                    out.append(
                        SanityIssue(
                            case.case_id,
                            case.task,
                            ERROR,
                            "expected_memory.values",
                            f"{v!r} 不是 kp_index 的 canonical name —— "
                            f"会导致 recalled/used 恒 False 的口径错配（应写规范名，如「图」而非「图论」）",
                        )
                    )
            # ★ 粒度 lint（2026-10-08 review M10，接 #26）：**正样本**的 `values` 必须是
            #   具体考点（`topic` / `point`），不能是章名（`domain`）或课程根节点（`subject`）。
            #   为什么只管正样本：`recalled` 是**子串包含**判定，章名会被它下面任何
            #   一个具体 KP 满足 ⇒ 「召回成功」测不出「召回的是不是设计的那个薄弱点」。
            #   负样本（`should_be_recalled=False`）保留章名是**刻意**的：偏松匹配让它更难通过，
            #   方向保守，不存在假通过（#26 已披露）。
            #   ★ 没有这条 lint，D8 的「收到具体考点」只是人工承诺 —— 改回 `图` 依旧 ERROR 0。
            if em.should_be_recalled:
                from core.kp_vocab import node_kinds as _node_kinds  # 局部导入：core 侧较重

                kinds = _node_kinds()
                for v in em.values:
                    if kinds.get(v) in ("domain", "subject"):
                        out.append(
                            SanityIssue(
                                case.case_id,
                                case.task,
                                ERROR,
                                "expected_memory.values",
                                f"{v!r} 是 {kinds[v]}（粗粒度）节点，而这是正样本 —— "
                                f"子串判定下任何子考点都算召回，请写具体薄弱点（如「图的存储」而非「图」）",
                            )
                        )
        if em.should_be_recalled is None:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "expected_memory.should_be_recalled",
                    "未标注 —— 无法区分正样本/负样本，recalled_pass 会失真",
                )
            )

    # —— expected_answer_property ——
    if eap is None:
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "expected_answer_property",
                "缺失 —— correct 无从机械判定",
            )
        )
    elif eap.forbidden_values is None:
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "expected_answer_property.forbidden_values",
                "未标注（若确无错误值请显式写 []）—— 缺失会使 correct 退化为 used 的副本",
            )
        )
    elif em is not None and em.values:
        overlap = sorted(set(eap.forbidden_values) & set(em.values))
        if overlap:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "expected_answer_property.forbidden_values",
                    f"与 expected_memory.values 重叠 {overlap} —— 同一值既期望又禁止，判定必自相矛盾",
                )
            )

    # —— setup_conditions（case-validity，2026-10-06 Step 5）——
    #   ★ 为什么也要求标注：A 段的前置条件（低分/高分次数）若**不声明**，
    #     则「B 段没召回」无法区分「前置条件没凑成」与「产品失败」——
    #     而前者是 grading LLM 的随机性，后者才是产品问题。缺它 ⇒ 结论不可信。
    sc = case.gold.setup_conditions
    if sc is None or not sc.is_valid():
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "setup_conditions",
                "缺失或未约束任何项 —— 无法区分「前置条件没凑成」与「产品失败」"
                "（至少标 min_grade_calls 或 grade_score_bands）",
            )
        )
    elif sc.grade_score_bands or sc.min_grade_calls is not None or sc.max_grade_calls is not None:
        if sc.grade_score_bands:
            for band in sc.grade_score_bands:
                lo, hi = band
                if not (0 <= lo <= hi <= 100):
                    out.append(
                        SanityIssue(
                            case.case_id,
                            case.task,
                            ERROR,
                            "setup_conditions.grade_score_bands",
                            f"区间 ({lo},{hi}) 非法 —— 得分是 0–100 制",
                        )
                    )
        # ★ 「空标」检测（2026-10-07）：`min_grade_calls: 0` 单独存在时**永不失败**
        #   （`len(calls) < 0` 不可能成立），但它又能骗过 `is_valid()`（字段非 None）。
        #   于是 gold_sanity 全绿、case 却处于「声明了前置条件但其实没校验」状态 ——
        #   mem-005「全新用户无写入」正是靠这条前置条件自证，写 `min: 0` 时它自证不了。
        if sc.min_grade_calls == 0 and sc.max_grade_calls is None and not sc.grade_score_bands:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "setup_conditions.min_grade_calls",
                    "min_grade_calls=0 单独存在是**永真**（次数不可能 < 0）⇒ 前置条件等于没校验。"
                    "若意图是「A 段一次批改都不许发生」，请改写成 min:0 + max:0",
                )
            )
        # 上下限互相矛盾 ⇒ validity 恒 False，该 case 永远只能记 case_invalid
        if (
            sc.max_grade_calls is not None
            and sc.min_grade_calls is not None
            and sc.max_grade_calls < sc.min_grade_calls
        ):
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "setup_conditions.max_grade_calls",
                    f"上限 {sc.max_grade_calls} < 下限 {sc.min_grade_calls} —— 前置条件不可能成立",
                )
            )
        # bands 要求逐次对分（隐含「至少 len(bands) 次」），上限比它小 ⇒ 同样不可能成立
        if sc.grade_score_bands and sc.max_grade_calls is not None:
            if sc.max_grade_calls < len(sc.grade_score_bands):
                out.append(
                    SanityIssue(
                        case.case_id,
                        case.task,
                        ERROR,
                        "setup_conditions.max_grade_calls",
                        f"上限 {sc.max_grade_calls} < grade_score_bands 要求的 "
                        f"{len(sc.grade_score_bands)} 次 —— 两者不可能同时满足",
                    )
                )


def _check_structure(case: TaskCase, out: list[SanityIssue]) -> None:
    # ★ memory 的「至少 2 轮」按**全会话合计**算（2026-10-06 修）：
    #   跨会话语义下每段会话可以只有 1 轮（如 A 段批改 1 句、B 段提问 1 句），
    #   但**合计**仍需 ≥2 轮，否则构不成「写记忆 → 跨会话召回」的链路。
    #   旧口径用 `case.all_turns`（= turns，只有各段首句）会把合法跨会话 case 判成 ERROR。
    if case.task == "memory" and len(case.all_sessions_flat) < 2:
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "turns",
                "memory 至少需 2 轮（跨会话合计；每段会话可仅 1 轮）",
            )
        )
    if not case.query.strip():
        out.append(SanityIssue(case.case_id, case.task, ERROR, "query", "缺失"))


# ── 主流程 ────────────────────────────────────────────────


def run_sanity(cases: list[TaskCase]) -> SanityReport:
    """对全部 case 跑检查。资产解析与生成器同源（`task_eval.assets`）。"""
    # 局部导入防成环 + 600 行上限（Task 7 裁定：宁可新建文件，不撑爆本文件）
    from evaluation.task_eval.gold_status_sanity import check_gold_answer_status

    report = SanityReport(n_cases=len(cases))
    kp_index = load_kp_index()
    items = parse_exam_items()
    question_ids = {it["question_id"] for it in items}
    stem_to_answer = {_norm_stem(it["stem"]): it["answer_key"] for it in items if it["stem"]}

    seen: dict[str, str] = {}
    for case in cases:
        if case.case_id in seen:
            report.issues.append(
                SanityIssue(case.case_id, case.task, ERROR, "case_id", "重复（case_id 必须唯一）")
            )
        seen[case.case_id] = case.task

        _check_structure(case, report.issues)
        _check_field_ownership(case, report.issues)
        _check_gold_source_ref(case, report.issues)
        check_gold_answer_status(case, report.issues)
        if case.task in ("qa", "generate"):
            _check_kp(case, kp_index, report.issues)
        if case.task == "generate":
            _check_generate(case, report.issues)
        if case.task == "grade":
            _check_grade(case, stem_to_answer, report.issues)
        if case.task == "verify":
            _check_verify(case, question_ids, report.issues)
        if case.task == "memory":
            _check_memory(case, kp_index, report.issues)

    # ★ 集合级检查（修 #7）：**单条**人工分是 0 或 100 完全合法，退化是**分布**性质 ——
    #   所以这里按整个 grade 集判，而不是逐条报（逐条会把 15 条全标黄，淹没真信号）。
    _check_grade_score_spread(cases, report.issues)
    return report


def _check_grade_score_spread(cases: list[TaskCase], out: list[SanityIssue]) -> None:
    """grade 集的人工分是否**两极退化**（⇒ `score_tolerance@±10` 不可判）。"""
    from evaluation.task_eval.metrics import degenerate_gold

    scores = [
        c.gold.human_score for c in cases if c.task == "grade" and c.gold.human_score is not None
    ]
    if not scores:
        return
    degenerate, n_distinct = degenerate_gold(scores)
    if not degenerate:
        return
    out.append(
        SanityIssue(
            "<dataset>",
            "grade",
            PENDING,
            "human_score",
            f"{len(scores)} 条人工分只有 {n_distinct} 个不同取值（两极）⇒ "
            "`score_tolerance@±10` 判为**不可判**（±10 无中间地带可判别）。"
            "★ 这不是「待人工补标」：L3 语料 674/674 全是 2 分选择题、case 学生作答仅 1 个字母 "
            "⇒ 无部分分可标。正确处置是改用 **`verdict_agreement`**（结论一致率）当 Grade 头号指标，"
            "报告已自动输出该值。",
        )
    )


def render(report: SanityReport) -> str:
    lines = [f"# Gold Sanity Check（{report.n_cases} 条 case）", ""]
    status = "✅ PASS" if report.ok else "❌ FAIL（存在非法 gold，禁止进 0B）"
    lines.append(
        f"**结论：{status}** —— ERROR {len(report.errors)} · PENDING {len(report.pendings)}"
    )
    lines.append("")
    if report.errors:
        lines.append("## ERROR（gold 非法，会污染 0B）")
        lines.append("")
        lines.append("| case_id | task | field | 说明 |")
        lines.append("|---|---|---|---|")
        for i in report.errors[:40]:
            lines.append(f"| {i.case_id} | {i.task} | {i.field_name} | {i.message} |")
        lines.append("")
    pend_by_field: dict[str, int] = {}
    for i in report.pendings:
        pend_by_field[f"{i.task}.{i.field_name}"] = (
            pend_by_field.get(f"{i.task}.{i.field_name}", 0) + 1
        )
    if pend_by_field:
        lines.append("## PENDING（draft 未标注 —— 不算失败，0B 前需补齐）")
        lines.append("")
        for k, v in sorted(pend_by_field.items()):
            lines.append(f"- `{k}`：{v} 条")
        lines.append("")
    # ★ 集合级问题**必须把消息打出来** —— 它不像逐条 PENDING 那样是同类噪声，
    #   一条消息里就带着处置指引；只报"1 条"等于没提醒。
    dataset_issues = [i for i in report.pendings if i.case_id == "<dataset>"]
    if dataset_issues:
        lines.append("## 集合级 PENDING（分布性质，逐条看不出来 —— 必须处置或明确披露）")
        lines.append("")
        for i in dataset_issues:
            lines.append(f"- **{i.task}.{i.field_name}** —— {i.message}")
        lines.append("")
    return "\n".join(lines)


def _stem_only(text: str) -> str:
    """截到**第一个选项行之前**。

    ★ 2026-10-06 修：Grade 的 `question_stem` 现在**含选项**（题干+选项+作答，才自包含），
      而真题索引 `stem_to_answer` 的键是 `items.md` 的**纯题干** ⇒ 直接比对必然匹配不上，
      会让 sanity 把 15 条合法 case 全判成 ERROR（**检查器自身的口径错配**）。
      故比对前先把选项部分截掉。
    """
    m = re.search(r"(?:^|\n)\s*A\s*[.、．]", str(text or ""))
    return str(text or "")[: m.start()] if m else str(text or "")


def _norm_stem(text: str) -> str:
    return "".join(_stem_only(text).split()).casefold()


def sanity_for_demo(task: str | None = None, demo_dir: str | Path | None = None) -> SanityReport:
    from evaluation.task_eval.cases import load_demo

    return run_sanity(load_demo(task, demo_dir=demo_dir))


__all__ = [
    "ERROR",
    "PENDING",
    "SanityIssue",
    "SanityReport",
    "TASKS",
    "render",
    "run_sanity",
    "sanity_for_demo",
]
