"""Phase 0 任务级评测：case 契约与加载（统一 Case Loader）。

设计边界（见 `docs/EFFECT_PLAN.md` §2.B）：
- 本包只做**任务效果测量**（QA / Generate / Grade / Verify / Memory），
  与 `scripts/agent_behavior_gate.py` 的**安全/行为门禁**职责分离、互不混合。
- case 来源与 schema 统一，供 gate 与 task_eval 共用（gate 本轮暂不改读，见决策 #4）。
- 本模块**不 import rag / agents**，只做纯数据契约与加载，保证可离线单测。

case schema（冻结 v1，见 evals/datasets/demo/README.md）
------------------------------------------------------
每条 case 一行 JSON，文件首部允许 `#` 注释头（沿用 sample_408.jsonl 约定）。

必填：case_id / task / query
选填：task_mode / turns / subject / notes / gold / gold_status / needs_review

`gold` 子对象按 task 取用不同字段（缺失即为 None，指标侧按「不适用」处理）：
- qa      : gold_points[] · expected_kp[] · reference
- generate: expected_kp[] · expected_difficulty · gold_answer
- grade   : question_stem · student_answer · human_score(0-100) · full_marks
- verify  : expected_question_ids[]
- memory  : expected_memory · expected_answer_property（见下）

memory 的 gold 契约（v1，2026-10-06 定稿）
------------------------------------------
Memory 的三项主指标**全部由机械判定**（judge 不参与，见 `memory_scorer.py`）：

    recalled_actual = 记忆卡里有没有 expected_memory.values
    recalled_pass   = recalled_actual == expected_memory.should_be_recalled
    used            = 回复里有没有 expected_memory.values 中任一
    correct         = used 且 回复里没有 forbidden_values 中任一

故 gold 必须给出「期望什么记忆」「回复该/不该出现什么」两类信息：

    "gold": {
      "expected_memory": {
        "type": "weak_topics",          // 只允许 weak_topics（产品当前唯一写入路径）
        "values": ["图论"],              // ★ 必须是 kp_index 的 canonical name
        "should_be_recalled": true      // false ⇒ 负样本：**不**召回才算通过
      },
      "expected_answer_property": {
        "forbidden_values": ["数据结构"]  // 必填，可为空数组；不得与 values 重叠
      }
    }

★ 为什么 `values` 必须是 canonical name：避免「LLM 输出 AVL树旋转 / gold 写 AVL树」
  这类字符串漂移导致 `in` 判定系统性假阴性。
★ 为什么 `should_be_recalled` 单独存在（而非复用 `must_reference_memory`）：
  它约束的是 **recalled**（期望有什么记忆），语义上属 `expected_memory`；
  且负样本必须能被表达，否则「期望不召回 + 实际不召回」会被误判为失败。
★ 为什么**不做缺省退化**：缺 `values` ⇒ used 只能靠 judge 猜；缺 `forbidden_values`
  ⇒ correct 退化成 used 的副本 —— 两者都与「指标必须可机械复现」直接冲突，
  故由 `gold_sanity` 强制校验为**错误**，而非静默降级。


★ `gold_status` 三态：draft（脚本预填，未经人工）→ reviewed（人工审核过）→ frozen（冻结）。
Phase 0 报告必须声明用的哪一态；`draft` 只可用于 0A smoke，不得出论文数字。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TASKS: tuple[str, ...] = ("qa", "generate", "grade", "verify", "memory")

# 各 task 的 gold 字段白名单：用于校验与「缺字段 → 不适用」判定
GOLD_FIELDS: dict[str, tuple[str, ...]] = {
    "qa": ("gold_points", "expected_kp", "reference"),
    "generate": ("expected_kp", "expected_difficulty", "gold_answer"),
    "grade": ("question_stem", "student_answer", "human_score", "full_marks"),
    "verify": ("expected_question_ids",),
    "memory": ("expected_memory", "expected_answer_property", "setup_conditions"),
}

# Memory 的 expected_memory.type 白名单。
# ★ 只允许 `weak_topics`：这是产品**当前唯一真实存在**的画像写入路径
#   （`abuild_memory_card` 只读 weak_topics，而它由 grade episodes 派生）。
#   不预留其他 type —— 预留但无写入路径的 type 会诱导写出「永远召不回」的 case，
#   把产品能力缺失记成产品失败。
MEMORY_TYPES: frozenset[str] = frozenset({"weak_topics"})

# demo 集固定路径（相对仓库根）
DEMO_DIR = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "demo"
DEMO_FILES: dict[str, str] = {task: f"{task}_cases.jsonl" for task in TASKS}


@dataclass
class ExpectedMemory:
    """Memory 任务：这条 case **期望** Store 里出现什么记忆（机械判定 recalled 用）。

    字段语义见模块 docstring「memory 的 gold 契约」。三个字段**都必填**，
    不做缺省退化 —— 缺任何一个都会让某项判定退回 judge 猜测。
    """

    type: str = ""  # 只允许 MEMORY_TYPES 中的值
    values: list[str] = field(default_factory=list)  # ★ kp_index canonical name
    should_be_recalled: bool | None = None  # True=正样本 / False=负样本

    @classmethod
    def from_dict(cls, raw: Any) -> ExpectedMemory:
        if not isinstance(raw, dict):
            return cls()
        should = raw.get("should_be_recalled")
        return cls(
            type=_as_str(raw.get("type")) or "",
            values=_as_str_list(raw.get("values")) or [],
            # ★ 不用 `or False`：缺字段必须保持 None（可校验为「未标注」），
            #   否则「漏填」会被静默当成「负样本」，口径颠倒且无告警。
            should_be_recalled=bool(should) if isinstance(should, bool) else None,
        )

    def is_valid(self) -> bool:
        """三字段齐备且取值合法（供 `gold_sanity` 与 scorer 判「可判定」）。"""
        return (
            self.type in MEMORY_TYPES and bool(self.values) and self.should_be_recalled is not None
        )


@dataclass
class ExpectedAnswerProperty:
    """Memory 任务：回复的**正确性属性**（机械判定 used/correct 用）。

    - `used`：回复是否体现期望记忆 —— 由 `ExpectedMemory.values` 决定（**不在此重复定义**，
      消除「双写两处、改一处忘另一处」的漂移源）；
    - `correct`：`used` 且回复**不含**任何 `forbidden_values`。
      列表为空 ⇒ `correct ≡ used`（该退化是**显式标注**的，不是静默行为）。
    """

    forbidden_values: list[str] | None = None  # 必填（可为 []）；None = 未标注

    @classmethod
    def from_dict(cls, raw: Any) -> ExpectedAnswerProperty:
        if not isinstance(raw, dict):
            return cls()
        # ★ 区分「字段缺失(None)」与「显式空数组([])」：
        #   前者是**未标注**（应报 PENDING），后者是「无明确错误值」的**合法标注**。
        if "forbidden_values" not in raw:
            return cls(forbidden_values=None)
        return cls(forbidden_values=_as_str_list(raw.get("forbidden_values")) or [])

    def is_valid(self) -> bool:
        return self.forbidden_values is not None


@dataclass
class SetupConditions:
    """Memory 任务的**前置条件**（case-validity 契约，2026-10-06 Step 5 定稿）。

    为什么需要它（用户裁决）
    ------------------------
    case 的「预期条件」不能**假定**模型一定给出预期分数：

        A 段批改 → LLM judge/grading → 实际 score（**有随机性**）

    若 mem-006 假定「两次高分」却实际跑出 `100 / 52`，那是 **A 段没满足预设条件**，
    应报 `case validity = FAIL`，而**不是**判 Memory 产品失败 —— 否则 grading LLM 的
    随机性会污染 Memory 指标（把「前置条件没凑成」记成「产品不召回」）。

    字段语义（全部可选；缺 ⇒ 该项不校验）
    ------------------------------------
    - `min_grade_calls`：A 段**至少**要发生几次批改（少于 ⇒ 无效）。None=不校验。
    - `max_grade_calls`：A 段**至多**要发生几次批改（多于 ⇒ 无效）。None=不校验。
      ★ 为什么需要（2026-10-07）：`min_grade_calls=0` 在机械上是**永真**的
      （`len(calls) < 0` 不可能成立）。而 mem-005「全新用户无写入」的**负样本对照**
      想要的恰恰是「A 段确实一次批改都没发生」—— 只写 `min: 0` 时该前置条件
      其实没被校验过：若 A 段意外触发了批改，Store 里就有了画像，
      这条 case 测的就不再是「无记忆时不会凭空召回」。
      ⇒ 意图是「恰好 0 次」就写 `min: 0, max: 0`，让对照本身可验收。
    - `grade_score_bands`：A 段每次批改得分须落入的**区间**（长度=期望次数）；
      每项是 `(lo, hi)`，含端点。例：`[(60, 100), (60, 100)]` = 两次都 ≥60。
      得分抓不到（None）⇒ 该项**无效**（不能默认满足）。
    - `allow_missing_score`：抓不到分时是否容忍。默认 False（fail-fast）。

    ★ 与 `expected_memory` 的分工：
      `setup_conditions` 管 **A 段（写入前提）是否成立**；
      `expected_memory` 管 **B 段（召回）是否符合预期**。
      二者判定的对象不同 —— 故前置条件不成立时，**Memory 三项不进分母**（记 N/A），
      另记 `case_invalid`，与「产品失败」明确区分。
    """

    min_grade_calls: int | None = None
    max_grade_calls: int | None = None
    grade_score_bands: list[tuple[float, float]] | None = None
    allow_missing_score: bool = False

    @classmethod
    def from_dict(cls, raw: Any) -> SetupConditions | None:
        if not isinstance(raw, dict) or not raw:
            return None
        bands: list[tuple[float, float]] | None = None
        raw_bands = raw.get("grade_score_bands")
        if isinstance(raw_bands, list) and raw_bands:
            bands = []
            for b in raw_bands:
                if isinstance(b, (list, tuple)) and len(b) == 2:
                    lo = _as_float(b[0])
                    hi = _as_float(b[1])
                    if lo is not None and hi is not None:
                        bands.append((lo, hi))

        def _as_int(key: str) -> int | None:
            v = raw.get(key)
            return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

        return cls(
            min_grade_calls=_as_int("min_grade_calls"),
            max_grade_calls=_as_int("max_grade_calls"),
            grade_score_bands=bands,
            allow_missing_score=bool(raw.get("allow_missing_score", False)),
        )

    def is_valid(self) -> bool:
        """至少约束一项，否则视为「未标注」。"""
        return (
            self.min_grade_calls is not None
            or self.max_grade_calls is not None
            or bool(self.grade_score_bands)
        )


@dataclass
class Gold:
    """gold 标注容器。未标注字段保持 None，指标侧据此判「不适用」。"""

    gold_points: list[str] | None = None
    expected_kp: list[str] | None = None
    reference: str | None = None
    expected_difficulty: str | None = None
    gold_answer: str | None = None
    question_stem: str | None = None
    student_answer: str | None = None
    human_score: float | None = None
    full_marks: float = 100.0
    expected_question_ids: list[str] | None = None
    # —— memory（机械判定三项主指标所需）——
    expected_memory: ExpectedMemory | None = None
    expected_answer_property: ExpectedAnswerProperty | None = None
    # ★ case-validity：A 段（写入前提）是否成立（2026-10-06 Step 5）
    setup_conditions: SetupConditions | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> Gold:
        raw = raw or {}
        return cls(
            gold_points=_as_str_list(raw.get("gold_points")),
            expected_kp=_as_str_list(raw.get("expected_kp")),
            reference=_as_str(raw.get("reference")),
            expected_difficulty=_as_str(raw.get("expected_difficulty")),
            gold_answer=_as_str(raw.get("gold_answer")),
            question_stem=_as_str(raw.get("question_stem")),
            student_answer=_as_str(raw.get("student_answer")),
            human_score=_as_float(raw.get("human_score")),
            full_marks=_as_float(raw.get("full_marks")) or 100.0,
            expected_question_ids=_as_str_list(raw.get("expected_question_ids")),
            expected_memory=(
                ExpectedMemory.from_dict(raw["expected_memory"])
                if raw.get("expected_memory") is not None
                else None
            ),
            expected_answer_property=(
                ExpectedAnswerProperty.from_dict(raw["expected_answer_property"])
                if raw.get("expected_answer_property") is not None
                else None
            ),
            setup_conditions=SetupConditions.from_dict(raw.get("setup_conditions")),
        )

    def memory_mechanizable(self) -> bool:
        """Memory 三项能否**机械判定**（两个子对象都合法）。

        为 False ⇒ 该 case 的 memory 三维记 N/A，**不进主指标分母**，
        并由 `gold_sanity` 报 PENDING 促人工补齐 —— 绝不退回 judge 判定。
        """
        return bool(
            self.expected_memory
            and self.expected_memory.is_valid()
            and self.expected_answer_property
            and self.expected_answer_property.is_valid()
        )

    def has(self, name: str) -> bool:
        """该 gold 字段是否**已标注且非空**（用于「不适用 vs 失败」判定）。"""
        value = getattr(self, name, None)
        if value is None:
            return False
        if isinstance(value, (list, str)) and len(value) == 0:
            return False
        return True


@dataclass
class TaskCase:
    case_id: str
    task: str
    query: str
    task_mode: str = ""
    turns: list[str] = field(default_factory=list)
    # ★ Memory 专用（2026-10-06 Step 4）：**会话分组** —— 每个内层列表是一段
    #   **独立对话**（独立 thread）。空 ⇒ 退化为 `turns` 的单 thread 行为。
    #   为什么必须有：跨会话记忆只能由「A 段写 Store → B 段读 Store」证明；
    #   若把 A/B 放进同一个 thread，checkpointer 就能解释召回，**证不了 Store 起作用**。
    sessions: list[list[str]] = field(default_factory=list)
    subject: str = ""
    notes: str = ""
    gold: Gold = field(default_factory=Gold)
    gold_status: str = "draft"
    needs_review: list[str] = field(default_factory=list)

    @property
    def all_turns(self) -> list[str]:
        """实际要跑的多轮输入：有 turns 用 turns，否则退化为单轮 query。"""
        return list(self.turns) if self.turns else [self.query]

    @property
    def all_sessions(self) -> list[list[str]]:
        """执行用的**会话分组**：有 `sessions` 用它，否则把 `turns` 叠成一段会话。

        ★ 单 thread 语义（无 `sessions`）与跨会话语义（有 `sessions`）在这里统一：
          调用方（`runner._run_agent`）只需拿 `all_sessions`，
          按「每段一个 thread」执行即可 —— 无 `sessions` 时自然退化为单段。
        """
        if self.sessions:
            return [list(s) for s in self.sessions if s]
        return [self.all_turns]

    @property
    def all_sessions_flat(self) -> list[str]:
        """**全部会话的所有轮次**，按顺序摊平（跨会话合计口径）。

        ★ 与 `all_turns` 的区别（易混，故单列）：`all_turns` 取的是 `turns` 字段
          （跨会话 case 里 `turns` 只放各段**首句**，是向后兼容的退化字段）；
          `all_sessions_flat` 则是**真正会被执行**的全量轮次
          （= `all_sessions` 摊平）。凡「要不要真的跑这些轮」的判定都应看它。
        """
        return [t for seg in self.all_sessions for t in seg]


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace("，", ",").split(",")]
        return [p for p in parts if p]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return None


def _as_str_list_2d(value: Any) -> list[list[str]] | None:
    """解析「会话分组」：`list[list[str]]`。

    ★ 只接受**二维**结构（`[["a","b"], ["c"]]`）—— 一维 `["a","b"]` 视为**未标注**，
      返回 None 而不是当成「一段会话」。理由：`sessions` 的语义是「这里显式声明了
      几段会话」，把一维误读成一段会让「跨会话」默默退化成「单会话」，
      属于**静默降级**，与项目 fail-fast 纪律冲突。缺失/畸形一律 None，
      由 `TaskCase.all_sessions` 决定回退到 `turns`。
    """
    if not isinstance(value, list):
        return None
    out: list[list[str]] = []
    for seg in value:
        if not isinstance(seg, list):
            return None  # 混入非列表元素 ⇒ 整条判定为畸形，不部分接受
        out.append([str(v).strip() for v in seg if str(v).strip()])
    return out or None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_case(raw: dict[str, Any], *, source: str = "") -> TaskCase | None:
    """把一行 JSON 解析为 TaskCase；缺关键字段返回 None（坏行跳过，不中断）。"""
    case_id = str(raw.get("case_id") or "").strip()
    task = str(raw.get("task") or "").strip().lower()
    query = str(raw.get("query") or "").strip()
    if not case_id or not query:
        logger.warning("case 缺 case_id/query，跳过：%s", source)
        return None
    if task not in TASKS:
        logger.warning("case %s 的 task=%r 不在 %s，跳过", case_id, task, TASKS)
        return None
    turns = _as_str_list(raw.get("turns")) or []
    sessions = _as_str_list_2d(raw.get("sessions"))
    if sessions and turns:
        # 两者都标注时以 sessions 为权威（turns 是向后兼容的退化字段）。
        flat = [t for seg in sessions for t in seg]
        if flat != turns:
            logger.info(
                "case %s: sessions 与 turns 不一致，以 sessions 为准（turns=%d 句 / sessions=%d 段 %d 句）",
                case_id,
                len(turns),
                len(sessions),
                len(flat),
            )
    return TaskCase(
        case_id=case_id,
        task=task,
        query=query,
        task_mode=str(raw.get("task_mode") or "").strip(),
        turns=turns,
        sessions=sessions or [],
        subject=str(raw.get("subject") or "").strip(),
        notes=str(raw.get("notes") or "").strip(),
        gold=Gold.from_dict(raw.get("gold")),
        gold_status=str(raw.get("gold_status") or "draft").strip(),
        needs_review=_as_str_list(raw.get("needs_review")) or [],
    )


def load_cases(path: str | Path, *, task: str | None = None) -> list[TaskCase]:
    """从单个 jsonl 加载 case；`#` 注释行与空行跳过，坏行只告警不中断。"""
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("demo 集不存在: %s", filepath)
        return []
    cases: list[TaskCase] = []
    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("%s 第 %d 行 JSON 失败: %s", filepath.name, line_num, e)
                continue
            case = parse_case(raw, source=f"{filepath.name}:{line_num}")
            if case is None:
                continue
            if task and case.task != task:
                logger.warning("case %s 的 task=%s ≠ 期望 %s，跳过", case.case_id, case.task, task)
                continue
            cases.append(case)
    logger.info("加载 %s: %d 条", filepath.name, len(cases))
    return cases


def load_demo(
    task: str | None = None,
    *,
    limit: int | None = None,
    demo_dir: str | Path | None = None,
) -> list[TaskCase]:
    """加载 demo 集。

    - `task=None`：按 TASKS 顺序合并五个文件（便于一次跑全量）。
    - `limit`：**每个 task 各取前 N 条**（0A smoke 用：每类 3 条）。
    """
    base = Path(demo_dir) if demo_dir else DEMO_DIR
    tasks = [task] if task else list(TASKS)
    out: list[TaskCase] = []
    for name in tasks:
        cases = load_cases(base / DEMO_FILES[name], task=name)
        if limit is not None:
            cases = cases[:limit]
        out.extend(cases)
    return out
