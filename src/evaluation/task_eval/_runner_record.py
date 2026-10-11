"""CaseRecord：§2.B.3 归档记录（从 runner.py 拆出，行为等价）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseRecord:
    """§2.B.3 定义的归档记录。字段名与文档保持一致，便于报告直接消费。"""

    case_id: str
    task: str
    task_mode: str
    query: str
    turns: list[str] = field(default_factory=list)

    # —— 原始自动量（报告只用这些）——
    kp_hit: bool | None = None
    kp_mrr: float | None = None
    category_hit: bool | None = None
    pack_nonempty: bool = False
    pack_len: int = 0
    evidence_count: int = 0
    exam_hit: bool = False
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0

    # —— 判分量 ——
    generation_ok: bool = False
    final_quality: float | None = None
    # ── Generate 交付五项（§3.1 v1.0 冻结口径，2026-10-06 按用户裁决重构）──
    # 均为三态：True 通过 / False 未过 / **None 不适用（从分母剔除）**
    gen_structure: bool | None = None  # 结构完整率：题干+选项/题型结构+标准答案+解析
    gen_answerability: bool | None = None  # 答案可判定率：存在明确可验证答案
    gen_coverage: bool | None = None  # 知识点覆盖率（= kp_hit；无可靠 expected_kp 则 N/A）
    gen_correctness: bool | None = None  # 内容正确率（校准后质量判断 final_quality≥阈值）
    gen_difficulty: bool | None = None  # 难度匹配（本批全 N/A：query 未指定难度）
    # ★ Verify 的行为层三判据（D14）：§3.1 冻结的头号指标 `question_id_recall@k` 不可计算（#20/D7），
    #   而 `final_quality≥4` 在 verify 上测的是**检索覆盖**（未达成 case 的诚实拒答是正确行为）
    #   ⇒ 由这三条把 §6 的 Verify 行 gate 住。None = **没测**（无回复 / 探针跑），不是"没出题"。
    ver_fabricated: bool | None = None  # 仍出题（编了新练习题）—— §6 的**硬条件**：必须 0
    ver_exam_item_cited: bool | None = None  # L1：给出可核对的真题条目（年份 + 题号/题干）
    ver_exam_year_only: bool | None = None  # L2：只报年份/来源与考点归属（与 L1 互斥）
    failure_reason: list[str] = field(default_factory=list)
    # ★ Task 8 Step 5：judge **单独**给、且没有 tier-0 证据支撑的检索层原因落这里
    #   （`judge.py.split_retrieval_layer_reasons`）。它与 `failure_reason` 同构、
    #   但**不参与** `pick_primary_failure`、不进任何归因统计 —— 只作「机械 vs 主观」对照，
    #   沿用 `judge_memory_*` 三个字段已验证过的隔离模式。
    #   ★ 老归档**没有**这个键 ⇒ 读它时按「未隔离过的旧口径」处理，不许回填、不许与新数据并列。
    judge_failure_reasons: list[str] = field(default_factory=list)
    primary_failure: str = "none"

    # —— memory（仅多轮 case；**机械判定**，judge 不参与）——
    #    `memory_retrieved` 语义 = `recalled_pass`（**与期望对齐**后的结果）。
    #    负样本（gold 期望不召回）时，`recalled_actual=False` 是**通过** ⇒ 记 True。
    #    故单纯看 `memory_retrieved=True` 不能推断「召回发生了」，
    #    要判「实际有没有召回」请看 `memory_recalled_actual`。
    memory_retrieved: bool | None = None
    memory_used: bool | None = None
    memory_correct: bool | None = None
    # —— memory 诊断字段（不进任何比率，供排查与复算）——
    memory_recalled_actual: bool | None = None
    memory_hit_values: list[str] = field(default_factory=list)
    memory_forbidden_hits: list[str] = field(default_factory=list)
    memory_cards: list[str] = field(default_factory=list)
    # judge 对三维的**主观判断**（已被护栏隔离，仅作「机械 vs 主观」对照）
    judge_memory_retrieved: bool | None = None
    judge_memory_used: bool | None = None
    judge_memory_correct: bool | None = None
    # —— case validity（A 段前置条件验收，2026-10-06 Step 5）——
    #   `validity_valid=False` ⇒ 前置条件没成立（如要求两次高分、实际 100/52），
    #   该 case 的 Memory 三项记 N/A（**不进分母**），另标 `case_invalid`。
    #   ★ 与「产品召回失败」严格区分：这是 **case 没凑成**，不是产品问题。
    validity_valid: bool | None = None
    validity_reason: str = ""
    grade_scores: list[dict[str, Any]] = field(default_factory=list)
    # ★ 逐轮执行日志（2026-10-07 Step 9）：`{session, turn, input, reply, tools, grade_scores}`
    #   用途：`case_invalid`（如「A 段批改次数 1 < 期望下限 2」）必须能归因到**具体哪一轮**、
    #   以及那一轮是「没调批改工具」还是「调了但没抓到分」—— 两者的论文含义不同。
    #   旧归档没有该字段 ⇒ 按空处理，不要回填。
    turn_log: list[dict[str, Any]] = field(default_factory=list)
    # ★ 本次跑在 Store 里真正写下的 episodes（清理前读）：`{topic, score, knowledge_points, type}`
    #   用途：判定「前置条件满足却没有记忆卡」是不是 **KP 分散**造成的
    #   （`MEMORY_WEAK_MIN_HITS=2` 要求同一 KP 命中两次）。老归档没有该字段 ⇒ 按空处理。
    # ★★ `episodes` 为空有两种**完全不同**的来源，故另存两个标志位（2026-10-08 review I3）：
    #   `episodes_read_failed` —— 清理前那次读取**抛错**了（取证通道自己坏了 ⇒ 写没写无从知道）；
    #   `memory_write_missing` —— 读没坏、Store 也开着、A 段确有批改，却一条都没读到
    #     ⇒ 「写入证据缺失」。★ 这**不等于**「环境挂了」：缺陷 C（`record_grade` 接线断）
    #     与 TEI `/embeddings` 502 的症状一模一样，而 `memory/safe.py` 只留一行 WARNING。
    episodes: list[dict[str, Any]] = field(default_factory=list)
    episodes_read_failed: bool = False
    memory_write_missing: bool = False
    # paired control：本 case 是否开着 Store（False=对照组）
    store_enabled: bool = True

    # —— 派生（仅供调试，不进报告）——
    retrieval_ok: bool = False
    # 值域来自 retrieval_probe（`retrieval_probe.py:66,140,149`）：
    #   `ok`（探针拿到非空 context）/ `empty`（正常查到空）/ `error`（探针抛错，已收敛不外泄）
    #   `""` = 老归档未知，不得回填。
    # ★ 刻意**不叫** `route_error`：`judge.mechanical_reasons_from_record` 已经在比较 `== "error"`，改名会把这条既有
    #   判定与后续归因链同时打断。
    # ★ 实测（2026-10-08：27 份 `evals/results/task_eval/*.jsonl` / 367 条记录）：
    #   `ok`×309、`empty`×34、**`error`×0**，另有 24 条该键缺失。
    #   ⇒ `error` 目前只存在于 `retrieval_probe.py:66` 的代码默认值里，`judge.mechanical_reasons_from_record` 那条分支
    #   **从未被触发过**。所以 B7 要修的不是「加一个值」，而是「让 `error` 真的可达」
    #   （BM25 把抛错咽成空结果），并且 Task 8 的归因门必须为这条分支自带取证。
    # ★ v1.3（裁定 R4）：`error` 自本修复轮起由**消费侧**产出 —— `run_case` 读 `query_failures`，
    #   经 `map_route_failures` 只升不降（探针自报 `ok`/`empty` + 有失败 ⇒ `error`）。
    retrieval_status: str = ""
    # ★ B7 消费侧（v1.3）的**凭据**：本次探针期间路由侧记下的失败原文
    #   （`VectorStoreManager.query_failures`，形如 `"<集合>: <异常类型>"`）。
    #   `run_case` 用它经 `map_route_failures` 把 `retrieval_status` 升为 `error`，
    #   清单本身**只作凭据**：与 `judge_failure_reasons` 同构 ——
    #   **不进**任何比率的分子/分母、**不进** `pick_primary_failure`、
    #   **不参与** `report.py`/`metrics.py`/`build_claim_ledger.py` 的任何计算路径（Task 8 修复轮 F2 已核查）。
    #   ★ 老归档**没有**这个键 ⇒ 读它时按「未消费过的旧口径」处理，不许回填。
    route_failure_notes: list[str] = field(default_factory=list)
    # ★ 状态枚举取代自报布尔（EVIDENCE_CHAIN.md §5 B2/B4）。
    #   空串 = 该归档跑在写这个字段之前的代码上 = **未知**，不得按 `off`/`not_attempted` 猜。
    rerank_status: str = ""
    memory_read_status: str = ""
    # ★ 修复轮 F5：**聚合之前**的逐轮原样留痕（`agents.teaching_graph` 的读链明细，按轮序）。
    #   为什么聚合之外还要留明细：`aggregate_memory_read_status` 的第 1 条规则是
    #   「有卡 ⇒ `success`」（正面物证优先），它**会压掉**其它轮报上的 `failed` ——
    #   只看聚合值就再也问不出「这一 case 里到底有没有哪一轮读过链坏过」。
    #   明细落盘后两者可**一一对应**：`memory_read_statuses=["failed","success"]` +
    #   `memory_read_status="success"` 是**合法**组合，而不是矛盾。
    #   ★ append-only（只由 `run_case` 写一次、来自捕获通道的快照）、**不进任何公式**：
    #     四态判定、Memory 三维、比率、`item_reasons` 一律只看聚合字段 `memory_read_status`。
    #   ★ 老归档没有这个键 ⇒ 按「未留痕」处理，不许回填、不许据此反推。
    memory_read_statuses: list[str] = field(default_factory=list)
    # 判据项为 None 时的原因（`not_applicable` / `missing_premise`）。R5 靠它区分两种 N/A。
    item_reasons: dict[str, str] = field(default_factory=dict)
    # provenance 补齐（§3 表）：只放非密钥字段与 hash，密钥原值一律不落。
    provenance: dict[str, Any] = field(default_factory=dict)
    retrieval_error: str = ""
    env_error: bool = False  # ★ 环境类错误（额度/鉴权）——必须从失败归因中剔除

    # —— ★ 检索侧「可离线重算」快照（2026-10-07 补，Step 9 前置）——
    #   洞（实测取证）：归档里检索侧只有**结果布尔**（`category_hit` / `kp_hit` / `exam_hit`），
    #   没存 top-k 每条命中文档的类目/KP/来源 ⇒ 修好指标后也**无法**离线重算老数字
    #   （#10 那 8 条就是这么被判成「只能重跑」的）；而 `tool_calls` 只有
    #   `{kind,status,query,docs}`，同样没带类目。
    #   另一半洞是**配置**：`phase1_baseline_v2.log` 里有「重排已按部署开关关闭」的 WARNING，
    #   说明那次跑的是「请求重排但没生效」—— 可没有 log 的 run（Step 5 两份就没有）**无从取证**。
    #   ⇒ 把「输入」与「配置」一起落盘，检索侧指标从此可复算、可比对。
    #   ★ 老归档没有这两个字段 ⇒ 按空处理（未知），不要拿当前配置回填。
    retrieval_cfg: dict[str, Any] = field(default_factory=dict)
    top_items: list[dict[str, Any]] = field(default_factory=list)

    # —— 原文与溯源 ——
    reply: str = ""
    hard_fails: list[str] = field(default_factory=list)
    gold: dict[str, Any] = field(default_factory=dict)
    gold_status: str = "draft"
    judge: str = ""
    agent_model: str = ""  # ★ 产出该输出的 agent 层模型（模型一变，旧数据不可比）
    code_version: str = ""
    golden_sha256: str = ""  # 黄金集内容哈希（冻结一致性：与 code_version 一起锁定基线）
    # ★ 修 #3（2026-10-07）：`code_version` 对 `src/` 的未提交改动只加 `-dirty` ⇒ 同一次
    #   改造里跑的多轮**全是同一个 `648d819-dirty`**，分不清谁跑在哪个提示词上。
    #   而 `PROMPT_SET_VERSION` 是提示词内容的 hash，改一个词就变（#8 就是这么漂的）
    #   ⇒ 把它落到每条 record 上，「结果 ↔ 提示词」这一跳不再依赖人工维护 §20 的表。
    #   ★ 老归档没有这个字段 ⇒ 读它的地方一律按 `""`（未知）处理，**不要**猜当前值。
    prompt_set_version: str = ""
    date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    # ★ 主指标字段（不是 property）。2026-10-07 修 #21：这里原先是一个**自己算一遍**的
    #   property（`retrieved ∧ used ∧ correct`），与 `memory_scorer` 里已按极性重写的
    #   `correct_use` **是两套实现**，而 `to_dict()` 用的正是这个旧的 ⇒ #4 的修复从未落盘，
    #   报告一直印旧口径（实测 ON 组印 2/6=0.333，应为 4/6=0.667）。
    #   现在公式只在 `metrics.memory_correct_use` 一处，本字段由 scorer 的判定结果写入。
    memory_correct_use: bool | None = None

    @property
    def rerank_used(self) -> bool:
        """★ B2：`rerank_used` 是**派生 property**，不再作为独立自报布尔存在。

        唯一真源是 tier-0 枚举 `rerank_status`：仅 `success ⇒ True`；
        `off`/`degraded`/`failed`/`""`（未知，老归档没写）一律 `False`。
        ⇒ 缺失前提（""）既不被折成普通失败、也不被折成成功；`off`（未执行重排）
          永不被误报为重排成功。因走 `__dict__`，本 property **不进** `to_dict()` 归档。
        """
        return self.rerank_status == "success"
