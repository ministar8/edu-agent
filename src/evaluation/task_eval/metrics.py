"""task-aware 指标：纯函数，无 IO、无 LLM，便于单测与复算。

口径全部来自 `docs/EFFECT_PLAN.md` §2.B / §3.1（v1.0 已冻结的规则）：
- `knowledge_coverage_pass = expected_kp ≠ ∅ AND expected_kp ⊆ retrieved_kp`；
  `expected_kp = ∅` → **N/A**（不是 FAIL）—— 避免「未标注」被算成「检索失败」。
- `difficulty_match_pass`：±1 档（**1–5 五档制**）。
- `score_tolerance@±10`：`|model − human| ≤ 10`（Grade 输出本就是 0–100）。
- Verify 的 `question_id_recall@5` 属 **Phase 1**（Phase 0 用 `exam_hit@5` 代理），
  但函数在此备好，Phase 1 直接可用。

★ 三态返回约定：`True` = 通过 / `False` = 失败 / `None` = **不适用**（缺 gold）。
报告侧必须把 `None` 单独计为 `n/a`，**不得并入失败率**。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

# ── failure_reason 枚举（§2.B.3 冻结）─────────────────────
FAILURE_REASONS: tuple[str, ...] = (
    "retrieval_miss",
    "retrieval_dropped",
    "evidence_pollution",
    "generation_wrong",
    "generation_incomplete",
    "format_violation",
    "tool_error",
    "memory_miss",
    # ★ `case_invalid`（2026-10-06 Step 5 新增）：**case 前置条件没成立**，
    #   与 `memory_miss`（产品没召回）**语义相反**，故必须单列。
    #   典型：mem-006 要求 A 段两次高分、实际跑出 100/52 ⇒ grading LLM 随机性所致，
    #   不是 Memory 产品失败。此类 case 的 Memory 三项记 N/A，不进分母。
    "case_invalid",
    "hallucination",
    "refusal",
    "none",
)

# primary_failure 的取用优先级：**最上游（根因）优先**，以便画因果链
# `retrieval_miss → evidence_insufficient → generation_incomplete`。
# 说明：`refusal` 排在末位 —— 它可能是**正确拒答**（见 §3.5 code 边界），
# 不宜盖过更具体的上游原因；`none` 永远最后。
# ★ `case_invalid` 排在最前：它是「样本本身无效」，比任何产品侧失败都更上游 ——
#   样本无效时，后面所有失败都不可信，故应压过一切。
_PRIMARY_PRIORITY: tuple[str, ...] = (
    "case_invalid",
    "tool_error",
    "retrieval_miss",
    "retrieval_dropped",
    "evidence_pollution",
    "memory_miss",
    "hallucination",
    "generation_incomplete",
    "generation_wrong",
    "format_violation",
    "refusal",
    "none",
)

# 难度字符串 → 1–5 档（文档口径是 1–5；demo 集允许写 basic/medium/hard 便于人工标）
_DIFFICULTY_MAP: dict[str, int] = {
    "basic": 2,
    "easy": 1,
    "medium": 3,
    "mid": 3,
    "hard": 4,
    "difficult": 5,
}

DIFFICULTY_TOLERANCE = 1  # ±1 档（v1.0 冻结）
GRADE_TOLERANCE = 10.0  # score_tolerance@±10（0–100 制，v1.0 拍板锁定）
QUALITY_PASS_THRESHOLD = 4  # final_quality ≥ 4 视为「好」


def pick_primary_failure(reasons: Sequence[str]) -> str:
    """按「最上游优先」从多个 failure_reason 里取主因；空则 `none`。"""
    present = {r for r in reasons if r in FAILURE_REASONS}
    for reason in _PRIMARY_PRIORITY:
        if reason in present:
            return reason
    return "none"


# ── 检索侧 ────────────────────────────────────────────────


def kp_coverage(expected_kp: Sequence[str] | None, retrieved_kp: Sequence[str]) -> bool | None:
    """`expected_kp ⊆ retrieved_kp`（必须全覆盖）；`expected_kp` 为空 → None（N/A）。

    ★ **祖先感知**（2026-10-05 修，属 §2.B.5 允许的「case runner 的 bug」）：
    考点 ID 是**层级制**（`co.storage` → `co.storage.cache`）。
    实测 `expected_kp=[co.storage]` 而命中 chunk 带 `co.storage.cache` —— 精确集合比较
    会判 False，但**父考点被其子节点覆盖在语义上是满足的**。
    故判定为「命中项 = 期望项 或其**子孙**」（按 id 前缀 `.` 分隔）。

    ⚠️ 该层级语义是对 §2.B.1 冻结公式的**解释**，非新增判据 —— 若你要求严格集合相等，
    把 `_kp_covered` 的子孙分支去掉即可（一处改动）。
    """
    if not expected_kp:
        return None
    have = {_norm(k) for k in retrieved_kp}
    want = {_norm(k) for k in expected_kp}
    return all(_kp_covered(e, have) for e in want)


def kp_mrr(
    expected_kp: Sequence[str] | None, retrieved_kp_per_item: Sequence[Sequence[str]]
) -> float | None:
    """第一个「覆盖任一 expected_kp」的文档的倒数排名；无 expected_kp → None。"""
    if not expected_kp:
        return None
    want = {_norm(k) for k in expected_kp}
    for rank, kps in enumerate(retrieved_kp_per_item, 1):
        have = {_norm(k) for k in kps}
        if any(_kp_covered(e, have) for e in want):
            return round(1.0 / rank, 4)
    return 0.0


def _kp_covered(expected: str, have: set[str]) -> bool:
    """期望考点是否被命中集合覆盖（精确 或 被其子孙覆盖）。"""
    if expected in have:
        return True
    return any(h.startswith(expected + ".") for h in have)


# kp_index 侧的学科码 → 门禁侧的类目键。★ `cn` 是 kp_index 用的码，
# `SUBJECT_TO_CATEGORY` 的键是 `network`，不对齐就会恒不命中（见 `category_hit`）。
_SUBJECT_ALIASES = {"cn": "network"}


def category_hit(subject: str, categories: Sequence[str]) -> bool | None:
    """top-k 内是否出现期望学科类目；未标或未登记学科 → **None（N/A，不进分母）**。

    ★ 2026-10-07 修：原实现 `SUBJECT_TO_CATEGORY.get(subject, subject)` 在查不到时拿
    **学科码本身**去和类目名比 ⇒ 恒不等 ⇒ **假失败**。实测：demo 的 `grade` / `verify`
    用 kp_index 的学科码 **`cn`**，而映射表的键是 **`network`**，各有 4 条被系统性记成
    `False`；`qa` / `generate` 用的是 `network`，所以一直全 True——同一函数在两个任务上
    表现不一致，正是它长期没被发现的原因。⇒「**测不到**」记 N/A，不能记「测错」。
    """
    if not subject:
        return None
    from evaluation.retrieval_gate import SUBJECT_TO_CATEGORY

    want = SUBJECT_TO_CATEGORY.get(_SUBJECT_ALIASES.get(subject, subject))
    if want is None:
        return None
    return any(c == want for c in categories)


def exam_hit_at_k(is_exam_flags: Sequence[bool], k: int = 5) -> bool:
    """top-k 内是否命中 L3 真题资产（**Phase 0 Verify 的主要代理**）。"""
    return any(is_exam_flags[:k])


def exam_rank(is_exam_flags: Sequence[bool]) -> int | None:
    """首条真题的排名（1-based）；无则 None。"""
    for rank, flag in enumerate(is_exam_flags, 1):
        if flag:
            return rank
    return None


# ── Memory 侧：**主指标只允许这一份公式**（2026-10-07 修 #21）────────
#
#   洞（实测）：`memory_scorer.MemoryJudgement.correct_use` 在 2026-10-07 的 #4 修复里
#   改成了「按样本极性分定义」，但 `runner.CaseRecord` 上**另有一个同名 property**
#   仍是旧三元 AND（`retrieved ∧ used ∧ correct`），而 `to_dict()` 用的是**那个 property**
#   ⇒ 极性版**从来没落到归档**，`report.py` 读的也是旧值。
#   实测差异：`phase1_memory_step5_store_on` 报告印 `correct_use = 2/6 = 0.333`（旧口径），
#   而 #4 之后应为 **4/6 = 0.667**；两份归档里 `mem-004`/`mem-005` 两条负样本
#   全部被旧公式判 False。
#   ⇒ 同一条指标存在两套实现时，「改了其中一处」等于没改。现在公式收敛到下面这一个函数，
#     scorer / record / report 三处都从这里取值；护栏 ⑱ 断言三者一致。


def memory_correct_use(
    *,
    should_be_recalled: bool | None,
    recalled_actual: bool | None,
    used: bool | None,
    correct: bool | None,
    recalled_pass: bool | None,
    forbidden_hits: Sequence[str] = (),
) -> bool | None:
    """记忆是否被**正确使用**（主指标；任一必需判定量为 None ⇒ N/A）。

    * **正样本**（`should_be_recalled=True`）：实际召回 ∧ used ∧ correct；
    * **负样本**（`False`）：未实际召回 ∧ **未误用**（回复不含任何 `forbidden_values`）。
      ★ 负样本**不看** `used`：什么都没召回时「回复里恰好出现该词」来自 RAG 证据或题面，
      不是用了记忆 —— 旧三元 AND 正是把这条判成失败（假阴性），
      同时又因「碰巧提到 ⇒ used=True」把空召回判成通过（假阳性）。
    """
    trio = (recalled_pass, used, correct, recalled_actual)
    if any(v is None for v in trio) or should_be_recalled is None:
        return None
    if should_be_recalled:
        return bool(recalled_actual) and bool(used) and bool(correct)
    return (not recalled_actual) and not tuple(forbidden_hits)


def memory_correct_use_from_record(rec: dict[str, Any]) -> bool | None:
    """从**归档 record** 推导主指标（与 `memory_correct_use` 同一份公式，无第二套）。

    ★ 为什么要从原始字段推导、而不是直接读 `rec["memory_correct_use"]`：
      2026-10-06 之前落盘的归档里存的是**旧口径**的值，直接读会把已修掉的假阴性
      继续印出来。原始字段（`memory_retrieved` / `memory_used` / `memory_correct` /
      `memory_recalled_actual` / `memory_forbidden_hits` + `gold.expected_memory`）
      都在，⇒ 报告可以按现口径重渲，**不改写归档**。
    """
    em = (rec.get("gold") or {}).get("expected_memory") or {}
    return memory_correct_use(
        should_be_recalled=em.get("should_be_recalled"),
        recalled_actual=rec.get("memory_recalled_actual"),
        used=rec.get("memory_used"),
        correct=rec.get("memory_correct"),
        recalled_pass=rec.get("memory_retrieved"),
        forbidden_hits=rec.get("memory_forbidden_hits") or (),
    )


# ── 生成侧（任务级）────────────────────────────────────────


def difficulty_match(expected: object, actual: object) -> bool | None:
    """难度是否 ±1 档内；任一缺失/无法解析 → None（N/A）。"""
    e = _as_difficulty(expected)
    a = _as_difficulty(actual)
    if e is None or a is None:
        return None
    return abs(e - a) <= DIFFICULTY_TOLERANCE


def score_tolerance(
    model_score: float | None, human_score: float | None, tol: float = GRADE_TOLERANCE
) -> bool | None:
    """`|model − human| ≤ tol`（默认 ±10，0–100 制）；缺任一 → None（N/A）。"""
    if model_score is None or human_score is None:
        return None
    return abs(float(model_score) - float(human_score)) <= tol


def score_mae(pairs: Sequence[tuple[float | None, float | None]]) -> float | None:
    """平均绝对误差（只统计两侧都有的样本）；无有效样本 → None。"""
    diffs = [abs(float(m) - float(h)) for m, h in pairs if m is not None and h is not None]
    if not diffs:
        return None
    return round(sum(diffs) / len(diffs), 3)


def question_id_recall(predicted: Sequence[str], gold: Sequence[str]) -> float | None:
    """`|Pred ∩ Gold| / |Gold|`（§3.1 冻结的统一公式）；gold 为空 → None。

    单题 gold 自然退化为 0/1，无需另立布尔口径。
    """
    if not gold:
        return None
    p = {_norm(x) for x in predicted}
    g = {_norm(x) for x in gold}
    return round(len(p & g) / len(g), 4)


def question_id_hit(predicted: Sequence[str], gold: Sequence[str]) -> bool | None:
    """`Pred ∩ Gold ≠ ∅`（答辩友好）；gold 为空 → None。"""
    if not gold:
        return None
    return bool({_norm(x) for x in predicted} & {_norm(x) for x in gold})


def quality_pass(
    final_quality: float | None, threshold: float = QUALITY_PASS_THRESHOLD
) -> bool | None:
    """`final_quality ≥ threshold`（默认 ≥4）；缺分 → None（N/A，非失败）。"""
    if final_quality is None:
        return None
    return float(final_quality) >= threshold


# ★ 说明性数字（满分 / 总分）先遮掉 —— 否则"关键词式"正则一定先撞上它们：
#   「总分 100 分，你得了 62 分」→ 100、「得分（满分 100）：62」→ 100（实测踩过）。
#   中文里「总分/满分」指的是**题目满分值**而非学生得分，故遮蔽是可辩护的；
#   产品自己的输出格式（`grading_core.format_grading_for_chat`）是「评分：40/100」，
#   不含这两个词，所以正常路径完全不受影响。
_MASK_FULLMARK_RE = re.compile(r"(?:满分|总分)\s*(?:为|=)?\s*\d{1,3}")
# 优先级：① 显式冒号式（最贴近产品输出）② 「你得 X 分」③ X/Y 比例 ④ 旧的宽松式兜底
_SCORE_EXPLICIT_RE = re.compile(
    r"(?:得分|评分|最终得分|分数)\s*[:：]\s*(\d{1,3})(?:\s*/\s*(\d{1,3}))?"
)
_SCORE_YOU_RE = re.compile(r"你(?:得|拿了|获得了|扣了)?\D{0,3}?(\d{1,3})\s*分")
_SCORE_RATIO_RE = re.compile(r"(\d{1,3})\s*/\s*(\d{1,3})")
_SCORE_LOOSE_RE = re.compile(r"(?:得分|评分|分数|总分)\D{0,4}(\d{1,3})(?:\s*/\s*(\d{1,3}))?")


def _to100(m: re.Match[str]) -> float | None:
    """把 (得分, 满分?) 两组折算到 100 制。单组正则（如「你得 X 分」）按百分制处理。"""
    score = float(m.group(1))
    second = m.group(2) if m.re.groups >= 2 else None
    full = float(second) if second else 100.0
    if not full:
        return None
    if full != 100.0:
        score = score / full * 100.0
    if score > 100.0:  # 明显不可能是百分制得分（如把 2013 这类年份当分数）
        return None
    return round(score, 2)


def parse_grade_score(text: str) -> float | None:
    """从 Grade 回复里尽力解析 0–100 得分（**best-effort**，判据需在报告中声明）。

    解析不到 → None（该 case 的 `score_tolerance` 记为 N/A，**不得算作失败**）。
    """
    if not text:
        return None
    masked = _MASK_FULLMARK_RE.sub(" ", text)
    for rex in (_SCORE_EXPLICIT_RE, _SCORE_YOU_RE, _SCORE_RATIO_RE, _SCORE_LOOSE_RE):
        m = rex.search(masked)
        if m:
            value = _to100(m)
            if value is not None:
                return value
    return None


# ── 汇总 ──────────────────────────────────────────────────


def rate(flags: Sequence[bool | None]) -> dict[str, float | int | None]:
    """通过率：**N/A（None）从分母剔除**。

    这是本项目所有布尔率指标的统一口径（Generate 四态判据的四态聚合见
    `predicates.common.rate` —— Task 4 起布尔合取/池化的旧副本已删，定义只在 registry）。

    ★ 返回**超集键**（`rate` 与 `value` 同值，另附 passed/failed/n/n_a）：
      历史上本函数曾先后用过 `rate` 与 `value` 两个键名，而消费方（`report._pct`
      读 `rate`、能力总表读 `value`）各认一个 —— 只留一个会让另一处**静默显示 n/a**。
      统一返回超集，避免再次出现「指标算对了但报告显示 n/a」。
    """
    passed = sum(1 for f in flags if f is True)
    failed = sum(1 for f in flags if f is False)
    n_a = sum(1 for f in flags if f is None)
    denom = passed + failed
    value = round(passed / denom, 4) if denom else None
    return {
        "rate": value,
        "value": value,
        "passed": passed,
        "failed": failed,
        "n": denom,
        "n_a": n_a,
    }


# ── Generate 交付判据（§3.1 v1.0；2026-10-06 按用户裁决重构）──────────────
#
# ★ 口径冻结（用户 2026-10-06 拍板，**不得偏离**）：
#   1. `expected_difficulty` 无可靠 gold 来源（黄金集无难度字段、query 0/32 提及难度）
#      ⇒ 记 **N/A**，`difficulty_match_pass` 该 case **不适用、不扣分**。
#      ❌ 禁止编默认难度（如 3）；❌ 禁止用系统自报的「理解/综合」反推 gold。
#   2. **不适用项（None）一律从分母剔除**（2026-10-06 定，仍不变）：
#      例：coverage=T, difficulty=N/A, answerability=T, correctness=T, structure=T
#          ⇒ 该题按 **4 项**判定，**不是**按 5 项打 80%。
#      ★ 聚合口径已于 2026-10-07（#2 定稿）定为**逐题 AND**（Task 4 起由
#        `predicates.registry` 的逐题复合 `pc.composite` 实现，对齐
#        `EFFECT_PLAN §3.1`「五项全过才算这题完整」）；原先的**项级池化**
#        （适用项通过数 / 适用项数，跨题累加）**降级为诊断**，不再当主指标 ——
#        因为池化会把「一道题崩掉 3 项」被另外十几道好题摊薄（实测同一归档：
#        池化 0.9423 vs 逐题 0.80，差 0.14 全在"稀释"里）。
#   3. `gold_answer` **不得**用黄金集示例题答案冒充生成题的 gold ⇒
#      `correctness_pass` 改用**校准后的质量判断**（judge 的 `final_quality`），
#      不引入独立 gold_answer。
#   4. 五项目标拆为**独立报告项**：结构完整率 / 答案可判定率 / 知识点覆盖率 /
#      内容正确率 / 难度匹配（后者本批全 N/A）。

# 结构四要素的机械判据（§3.1「题干 + 选项/要求 + 标准答案 + 解析 齐全」）
_STRUCTURE_STEM = re.compile(r"题干")
_STRUCTURE_ANSWER = re.compile(r"标准答案|参考答案")
_STRUCTURE_EXPLAIN = re.compile(r"解析|解题思路|错因")
# 「选项/题型结构」：有选项字母，或标了题型，或给出编号小问
_STRUCTURE_OPTIONS = re.compile(
    r"(?:^|\n)\s*[A-D]\s*[.、．)）]|类型\s*[：:]|(?:^|\n)\s*[（(]\s*[1-9]\s*[）)]"
)
# 答案不可判定的模糊表述
_VAGUE_ANSWER = re.compile(r"略|见解析|视情况|不确定|无法确定|自行|略述")


def structure_completeness(reply: str) -> dict[str, bool]:
    """结构四要素（题干 / 选项·题型结构 / 标准答案 / 解析）。"""
    text = str(reply or "")
    return {
        "stem": bool(_STRUCTURE_STEM.search(text)),
        "options_or_task": bool(_STRUCTURE_OPTIONS.search(text)),
        "answer": bool(_STRUCTURE_ANSWER.search(text)),
        "explanation": bool(_STRUCTURE_EXPLAIN.search(text)),
    }


def structure_pass(reply: str) -> bool:
    """四要素**齐全**才算结构完整（§3.1）。"""
    return all(structure_completeness(reply).values())


# ── 判据抽取 helper（predicates 包的唯一解析真源；分段正则复用 _STRUCTURE_*，无第二套）──
_ANSWER_LINE = re.compile(r"(?:标准答案|参考答案|答案)\s*[：:]\s*([^\n。；;]{0,40})", re.I)
_LETTER = re.compile(r"([A-D])")
_OPTION_LINE = re.compile(r"^\s*([A-D])\s*[.、．)）]\s*\S", re.M)
_ANALYSIS_KEY = re.compile(r"(?:所以|因此|故|答案[是为]?|正确)[^\n。]{0,12}?选?\s*([A-D])\b", re.I)
_DIFFICULTY_LINE = re.compile(
    r"(?:难度|难易程度)\s*[：:]\s*(基本|基础|简单|中等|适中|较难|困难|basic|easy|medium|hard)",
    re.I,
)


def option_letters(reply: str) -> list[str]:
    """选项**集合**（去重保序）。这里去重是对的：选项集本来就该是集合。"""
    seen: list[str] = []
    for m in _OPTION_LINE.finditer(str(reply or "")):
        k = m.group(1).upper()
        if k not in seen:
            seen.append(k)
    return seen


def answer_keys_of(reply: str) -> list[str]:
    """答案键序列 —— ★ **不去重、不取第一个**。

    数量本身就是判据：`标准答案：A、B` ⇒ `['A','B']` ⇒ 单选语义下不唯一 ⇒ fail。
    如果这里返回单个键（旧写法 `answer_key_of()`），「两个都算对」这个失败形状
    在读数阶段就被抹掉了，`gen_answer_key_validity` 只剩「键 ∈ 选项」半条契约。
    """
    m = _ANSWER_LINE.search(str(reply or ""))
    return [k.upper() for k in _LETTER.findall(m.group(1))] if m else []


def analysis_key_of(reply: str) -> str | None:
    """解析正文最后落到的那个选项（#33 产品规则「答案键与解析同结论」的评测化）。"""
    keys = [k.upper() for k in _ANALYSIS_KEY.findall(str(reply or ""))]
    return keys[-1] if keys else None


def difficulty_of(reply: str) -> str | None:
    """从生成题正文里抽难度档（`gen_difficulty` 的实际侧输入）。

    ★ 抽不出来 ⇒ 判据返回 `missing_premise` 而**不是** `fail`：解析器的失败不能记成
      产品的失败。`_as_difficulty()`（:664）已负责把中文档名映射到 1–5，这里只做抽取。
    """
    m = _DIFFICULTY_LINE.search(str(reply or ""))
    return m.group(1) if m else None


# ★ 分段名与 `structure_completeness` 用的是**同一批** `_STRUCTURE_*` 常量（本节上方）。
#   `difficulty` 是 Task 5 追加的第五段（`_DIFFICULTY_LINE`，本节上方）：它不是结构要素、
#   不进 `structure_completeness`，但 gen_difficulty 的契约点名了 `reply#difficulty`，
#   falsify 的 omit mutation 需要能删掉难度行 —— 分段知识仍然只有 metrics 一份。
_REPLY_PART_PATTERNS: dict[str, re.Pattern[str]] = {
    "stem": _STRUCTURE_STEM,
    "options_or_task": _STRUCTURE_OPTIONS,
    "answer": _STRUCTURE_ANSWER,
    "explanation": _STRUCTURE_EXPLAIN,
    "difficulty": _DIFFICULTY_LINE,
}


def strip_reply_part(reply: str, part: str) -> str:
    """删掉 reply 里某个语义片段的标识（Task 5 `omit_reply_part` 的唯一实现处）。

    「判据认为某段存在」与「夹具把那段抹掉」必须说同一种语言，否则会出现
    夹具删 A 段、判据读 B 段 的假红/假绿。未知片段名直接抛错，不静默返回原文。
    """
    pattern = _REPLY_PART_PATTERNS.get(part)
    if pattern is None:
        raise ValueError(f"未知的 reply 片段名：{part}")
    return pattern.sub("", str(reply or ""))


def rewrite_reply_part(reply: str, part: str, new_text: str) -> str:
    """替换某个语义片段的**整段**（label + 正文），不是只换 label（Task 5 Step 2.5）。

    `strip_reply_part` 只删 label 是**够用的**（`structure_completeness` 按 label 判存在）；
    但 rewrite 若也只换 label，旧正文会残留在后面被解析器读到，mutation 就不生效
    （实测：`flip_conclusion` 后 `analysis_key_of()` 仍返回 B，`gen_analysis_agreement` 保持
    pass，取证拿不到红）。段边界沿用 `_REPLY_PART_PATTERNS` 的同一批 label：从本 label
    匹配处开始，到**下一个别的** label 匹配处（或文本末）结束 —— 同名 pattern 的后续匹配
    是本段的延续（如选项块 A-D 的 B/C/D 行），不是边界。段尾紧邻下一 label 的空白原样
    保留，避免两段被拼进同一行。
    """
    pattern = _REPLY_PART_PATTERNS.get(part)
    if pattern is None:
        raise ValueError(f"未知的 reply 片段名：{part}")
    text = str(reply or "")
    m = pattern.search(text)
    if not m:
        return text
    start = m.start()
    ends = [
        hit.start()
        for name, rex in _REPLY_PART_PATTERNS.items()
        if name != part
        for hit in rex.finditer(text)
        if hit.start() > start
    ]
    end = min(ends) if ends else len(text)
    segment = text[start:end]
    return text[:start] + new_text + segment[len(segment.rstrip()) :] + text[end:]


def answerability_pass(reply: str) -> bool | None:
    """答案可判定率：是否存在**明确、可验证**的答案。

    判据：给出了「标准答案/参考答案」，且不是「略/见解析/视情况」这类模糊表述。
    （「答案是否真的唯一正确」属 `correctness_pass`，不在本条判定。）
    """
    text = str(reply or "")
    if not _STRUCTURE_ANSWER.search(text):
        return False
    m = re.search(r"(?:标准答案|参考答案)\s*[：:]\s*(.{1,80})", text, re.S)
    if not m:
        return False
    return not _VAGUE_ANSWER.search(m.group(1))


def degenerate_gold(values: Sequence[float]) -> tuple[bool, int]:
    """Grade 的 gold 是否**退化**（两极分布）—— 2026-10-07 修 #7。

    `score_tolerance@±10` 测的是「模型分与人工分在 ±10 内是否一致」。若人工分
    只有两个取值（实测 0B 的 15 条 = `{100: 8, 0: 7}`），那这道题实际在问
    「模型有没有也跟着说 0 或 100」—— **没有中间地带可供 ±10 去判别**，
    于是 `tolerance = 1.000` 会被读成"判分能力完美"，而它只证明了对齐二值标注。

    判据刻意简单可解释：**样本 ≥5 且不同取值 ≤2** ⇒ 退化。
    （不用"必须等于 0/满分"这类魔法阈值：只要取值 ≤2 个，无论是什么值，
    容差指标都没有判别力。）

    Returns
    -------
    (degenerate, distinct_count)
        样本 < 5 时返回 ``(False, n_distinct)`` —— 那是**样本不足**，不是退化，
        不该由本函数冒充判定。
    """
    distinct = {round(float(v), 2) for v in values if v is not None}
    if len(values) < 5:
        return False, len(distinct)
    return len(distinct) <= 2, len(distinct)


# 「答对」的分数线。**直接引用产品自己的定义**（`schema/grading.py`：
# `is_wrong` 的说明就是「score < 60 视为错误」）⇒ 评测器不自造阈值。
WRONG_SCORE_LINE = 60.0


def verdict_agreement(
    model_score: float | None,
    human_score: float | None,
    full_marks: float = 100.0,
) -> bool | None:
    """**结论一致率**：模型判"答对/答错"与人工是否一致。任一缺失 ⇒ None（N/A）。

    ★ 为什么本项目该用它当 Grade 头号指标（2026-10-07 修 #7）：
    L3 语料 **674/674 全是 2 分选择题**、demo 的 grade case 学生答案**全是 1 个字母**
    ⇒ 人工分只能是 0 / 满分，`score_tolerance@±10` 在这种二值 gold 上**没有可判别的
    中间地带**（它其实只在问"模型有没有也跟着说 0 或 100"）。
    而"对错"这件事在二值 gold 上是**完全合法**的标注 —— 所以合法的问题形式是
    **结论对不对**，不是**分数差多少**。

    与 `score_tolerance` 的关键差别（护栏 ③o 锁这条）：
    模型给 70、人工给 100 ⇒ 数值差 30，`tolerance` 判**失败**，
    但两者结论都是"答对" ⇒ `verdict_agreement` 判**通过** —— 后者才是我们想测的能力。
    """
    if model_score is None or human_score is None:
        return None
    model_says_right = model_score >= WRONG_SCORE_LINE
    human_says_right = human_score >= (full_marks / 2.0)
    return model_says_right == human_says_right


# ── Verify 的行为层判据（D14，2026-10-08 机械化）────────────────────────
#
# 为什么必须有：`EFFECT_PLAN §3.1` 给 Verify 冻结的头号指标 `question_id_recall@k`
# **在当前语料上不可计算**（#20：ingest 时没把 `question_id` 写进 metadata，D7 已裁决走披露），
# 而 §6 的占位门槛「≥80% `final_quality≥4`」在 verify 上是**指标效度错**：
# 实测 0B 与 Phase 1 都是 **0/15**，因为未达成的 case 全是 `exam_hit=False`
# （检索层没给真题证据），而那种情况下 agent **诚实说明"无法确认"是正确行为**
# ⇒ `final_quality` 在这里测的是**检索覆盖**，不是回答质量。
# ⇒ Verify 这一行改由下面两个可机械复现的断言把门（`fabricated` 是硬条件）。
#
# ★ 与历史人工读数的关系（必须一起披露，别装作一致）：`PHASE1_VERIFY.md` 记的
#   「仍出题 6/15→0/15」被 `verify_fabricated` **逐条复现**（case_id 完全相同）；
#   但「有真题信息 3/15→9/15」是**混级计数**（给出题干/题号 与 只列了年份来源文件
#   被数在一起），且人工件没留 case_id ⇒ 无法逐条对账。本判据改为**分两级**：
#   `exam_item_cited`（给出可核对的真题条目）与 `exam_year_only`（只报年份来源）。

_V_YEAR_RE = re.compile(r"(?:19|20)\d{2}\s*年")
_V_ITEM_RE = re.compile(r"第\s*\d+\s*题|\bQ\d{1,3}\b")
_V_EXAM_WORD_RE = re.compile(r"真题")
_V_TOPIC_RE = re.compile(r"考点|考查|涉及|归纳|变式|题型")
# 自我否定句：年份只是「来源文件 / 被列出的等年份」，**不算**给出真题条目。
# ★ 少了这层过滤，「未包含任何真题的年份、题号」这种句子会反过来制造假命中。
_V_DENIAL_RE = re.compile(
    r"仅作为|来源文件|来源列表|来源[:：]|等年份|未检索到|无法确认|并未给出|未给出"
)
_V_STEM_RE = re.compile(r"题干[：:]")
_V_ANSWER_KEY_RE = re.compile(r"(标准答案|参考答案)[：:]")
_V_GEN_ITEM_RE = re.compile(r"(\*\*题目\s*1\*\*|练习题|模拟题)")
# 表格式清单：`| 2021 | Q14 | 题干… |` —— 年份那一格**没有"年"字**，所以年份正则盖不到，
# 必须单独认（实测归档里 `ver-006` 就是这种形态，漏了它 L1 会假阴）。
_V_TABLE_ROW_RE = re.compile(r"^\|\s*(?:19|20)\d{2}\s*\|\s*Q?\d{1,3}\s*\|")


def verify_fabricated(reply: str) -> bool:
    """**仍出题**：在「问历年真题」的意图下生成了新练习题（题干 + 答案键 + 出题标题三者同现）。

    这是 §6 Verify 行的**硬条件**（必须为 0）—— 它测的正是 Verify 存在的意义：
    用户要历史真题时不得编新题。实测 0B 命中 6/15、Phase 1 命中 **0/15**，case_id 与
    `PHASE1_VERIFY.md` 的人工记录逐条一致。
    """
    text = str(reply or "")
    return bool(
        _V_STEM_RE.search(text) and _V_ANSWER_KEY_RE.search(text) and _V_GEN_ITEM_RE.search(text)
    )


def verify_exam_item_cited(reply: str) -> bool:
    """**L1**：给出可核对的真题条目 —— 同一行里既有年份、又有题号或题目描述。

    两种真实形态都要认（都是从归档里长出来的，不是设想）：
    散文式 `- 2010 年 第 33 题：…`、表格式 `| 2021 | Q14 | …`。
    ★ 判定是**逐行**的：跨行拼出来的"年份 + 题号"不算（否则整篇回复里随便两处凑成命中）。
    """
    for ln in str(reply or "").splitlines():
        s = ln.strip()
        if _V_TABLE_ROW_RE.match(s):
            return True
        if not s or not _V_YEAR_RE.search(s):
            continue
        if _V_ITEM_RE.search(s):
            return True
        if _V_EXAM_WORD_RE.search(s) and not _V_DENIAL_RE.search(s) and len(s) >= 25:
            return True
    return False


def verify_exam_year_only(reply: str) -> bool:
    """**L2**：只报出年份/来源文件与考点归属，没给到可核对的题目条目。

    与 L1 **互斥**（L1 成立就不算 L2）—— 否则一个回复同时命中两级，两个率就没法相加解读。
    L2 高、L1 低 的含义是"说得出发过什么方向、但给不出具体题" ⇒ 属检索覆盖不足，
    不是回答质量问题（这正是 #20 的那条链）。
    """
    if verify_exam_item_cited(reply):
        return False
    for ln in str(reply or "").splitlines():
        s = ln.strip()
        if _V_YEAR_RE.search(s) and (_V_TOPIC_RE.search(s) or _V_DENIAL_RE.search(s)):
            return True
    return False


# ── Memory 的可测性 / 配对对照（D15，2026-10-08）───────────────────────
#
# 为什么 §6 的 Memory 行**不写百分数门槛**：
#   * 0B 那批的 `gold` 里根本没有 `expected_memory` ⇒ 四率**全 N/A**（#9），
#     所以「≥80% correct-use」**无法按 Phase 0 回填** —— 回填不出一个当时没测的量。
#   * 新口径下可测正样本只有 **n=1**（§20.8.6）。n=1 上任何百分数都没有统计意义，
#     答辩被问「你这个 100% 是几条？」就崩（与 §9「硬上统计指标」的禁令同向）。
#   ⇒ 改为**三条结构断言**：① 配对成立（`paired_control_verdict`）
#     ② 每条被计入的正样本可追溯（`memory_traceable`）③ 报「可测率」作为披露量。


def memory_traceable(rec: dict[str, Any]) -> bool:
    """**断言 2**：这条 Memory record 的结论是不是**有证据支撑**的。

    要求四样都在：逐轮日志（能指出"哪一轮没调工具"）、记忆卡捕获通道、
    episodes 字段（OFF 臂**可以**是空列表，但字段必须在 ⇒ 区分「没写」与「没读」）、
    `store_enabled`（paired control 的自证）。
    ★ 不看 `memory_cards` 是否为空 —— 空卡是**合法结果**（负样本就该空）。
    """
    return bool(
        rec.get("turn_log")
        and "memory_cards" in rec
        and "episodes" in rec
        and isinstance(rec.get("store_enabled"), bool)
    )


def paired_control_verdict(
    on_records: list[dict[str, Any]], off_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """**断言 1**：Store ON/OFF 是不是真的**只差 Store** 这一个变量。

    只统计「两臂都 `validity_valid is True` 的正样本」= **交集** ——
    一条臂前置条件没凑成的 case 不参与配对（否则结论会被 case 有效性污染，#5/#18 都是这类）。
    对交集里每条 case 要求：ON 侧实际召回为真、OFF 侧为假；
    并额外报 OFF 侧**出现记忆卡**的条数 —— 那正是 **#24** 的机械探测器
    （旧实现只置 `agent.store=None`、进程级 store 还活着 ⇒ OFF 侧照样有卡，
    当时的「OFF 0 卡」其实是 #22 造成的假象，两个缺陷互相掩盖）。
    """

    def positives(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in records:
            em = (r.get("gold") or {}).get("expected_memory") or {}
            if em.get("should_be_recalled") is not True:
                continue
            if r.get("validity_valid") is not True:
                continue
            out[str(r.get("case_id"))] = r
        return out

    on, off = positives(on_records), positives(off_records)
    common = sorted(set(on) & set(off))
    ok: list[str] = []
    bad: list[str] = []
    off_has_card: list[str] = []
    for cid in common:
        a, b = on[cid], off[cid]
        if bool(a.get("memory_recalled_actual")) and not bool(b.get("memory_recalled_actual")):
            ok.append(cid)
        else:
            bad.append(cid)
        if b.get("memory_cards"):
            off_has_card.append(cid)
    return {
        "n_pairs": len(common),
        "n_ok": len(ok),
        "failed": bad,
        "off_has_card": off_has_card,
        # ★ 通过条件：至少一对、且**一对都不许有反例**；OFF 侧出现卡一律判失败
        "passed": bool(common) and not bad and not off_has_card,
        "note": "只统计两臂都满足前置条件的正样本；OFF 侧有卡即失败（#24 探测器）",
    }


# ── 内部 ──────────────────────────────────────────────────


def _norm(text: object) -> str:
    return str(text or "").strip().casefold()


def _as_difficulty(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        level = int(value)
        return level if 1 <= level <= 5 else None
    return _DIFFICULTY_MAP.get(str(value).strip().lower())
