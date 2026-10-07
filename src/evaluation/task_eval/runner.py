"""单条 case 的执行器：跑产品链路 + 检索探针 → 一条可归档的 record。

执行顺序（每条 case）：

    1) 跑真实 agent（多轮）          → reply / tool_payloads / hard_fails
    2) 跑检索探针（同策略、k=5）      → 元数据完整的证据包
    3) 机械判 `generation_ok`         → 只答「有没有产出合法结果」
    4) 机械收集 `failure_reason`      → 检索/工具层可自动判的部分
    5) （可选）LLM judge              → `final_quality` 与生成侧 failure_reason

★ 与 `agent_behavior_gate.py` 的边界：本模块**不复制**它的硬安全检查，
  只透传 `CaseResult.hard_fails` 作为 `generation_ok` 的一个否决项；
  安全门禁仍由 gate 负责（决策 #2：职责不混）。

★ `tool_calls` 的口径限制：`agent_behavior_smoke.run_turns` 只收集**能解析为
  JSON dict** 的 ToolMessage。`generate_practice_questions` 返回纯文本，故不会被
  计入 —— 因此 `tool_calls` 是「检索类工具调用」的近似，不是全量工具轨迹。
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.settings import settings
from evaluation.task_eval import memory_scorer, metrics
from evaluation.task_eval.cases import TaskCase
from evaluation.task_eval.retrieval_probe import RetrievalProbe, probe_retrieval

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]

# `generation_ok` 的机械判据（§2.B.3 冻结）
_GEN_REQUIRED_MARKERS = re.compile(r"题干|题目|标准答案|解析|答案[:：]|选项")
_GRADE_FIELD_RE = re.compile(r"得分|评分|分数|反馈|评语|扣分")

# 环境类错误（额度耗尽 / 鉴权失败 / 依赖不可用）——**不是 case 失败**。
# ★ 必须与 tool_error 区分：把「账号没额度」记成「工具报错」会污染 failure_reason 归因，
#   使 Phase 0 的「主要失败原因」失真（EFFECT_PLAN §2.B.5 只允许修环境/runner bug）。
_ENV_ERROR_MARKERS = (
    "Free quota exhausted",
    "AllocationQuota",
    "PermissionDeniedError",
    "AuthenticationError",
    "insufficient_quota",
    "invalid_api_key",
    # ★ 2026-10-05 实测补充：账号**欠费**（DashScope `code: Arrearage`，
    #   文案 "Access denied... overdue-payment"）。与「免费额度耗尽」是**两回事**：
    #   前者充钱即恢复，后者要改计费模式。但两者都属环境，都不该计入 case 失败。
    "Arrearage",
    "overdue-payment",
    "account is in good standing",
    # ★ 2026-10-06 实测补充：**检索/embedding 服务不可用**（TEI 容器停了）。
    #   缺这一条时，探针 run 会带着「检索全空」继续跑完 —— 实测跑了 12 分钟、
    #   全部 case 被记成 retrieval_miss，把「服务挂了」伪装成「能力不行」。
    #   ⇒ 必须与额度错误同级：**立即中止、不计失败**。
    "502 Bad Gateway",
    "Chroma query failed",
    "embedding failed",
    "embedding 失败",
    "Connection refused",
    "积极拒绝",
    "upstream connect failed",
    "Max retries exceeded",
)


def is_env_error(text: str) -> bool:
    """判断错误文本是否属**环境类**（额度/鉴权），而非 case 级失败。"""
    return any(marker.lower() in (text or "").lower() for marker in _ENV_ERROR_MARKERS)


def ensure_localhost_no_proxy() -> None:
    """把 localhost/127.0.0.1 加入 ``NO_PROXY``，让本机服务（TEI 等）**绕过代理**。

    ★ 为什么必须有（2026-10-06 实测教训）：本机环境设了
      ``HTTP_PROXY=http://127.0.0.1:55466``，于是**连 localhost 也走代理** ——
      代理处理不了 TEI，表现为 `502 Bad Gateway` / `RemoteProtocolError` / `Empty reply`，
      极易误判成「TEI 挂了」。
      ⇒ 只把**本机地址**排除在外；外部 API（DashScope 等）**仍走代理**，不受影响。
    """
    import os

    needed = ("localhost", "127.0.0.1", "::1")
    for key in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(key, "")
        items = [x.strip() for x in current.split(",") if x.strip()]
        for host in needed:
            if host not in items:
                items.append(host)
        os.environ[key] = ",".join(items)


def preflight_check() -> list[str]:
    """运行前预检外部依赖，返回问题列表（空 = 全部就绪）。

    ★ 为什么必须有（2026-10-06 实测教训）：TEI embedding 容器停掉后，
      检索链**不抛异常**，只返回空结果 ⇒ 探针 run 带着「检索全空」跑满 12 分钟，
      把「服务挂了」记成 `retrieval_miss`，伪装成「能力不行」。
      而 `retrieval_error` 是**空的**，事后的文本标记也检测不到。
      ⇒ 唯一可靠的办法是**花钱之前先探活**。
    """
    import httpx

    ensure_localhost_no_proxy()
    problems: list[str] = []
    if not getattr(settings, "USE_FAKE_EMBEDDING", False):
        base = str(getattr(settings, "EMBEDDING_API_BASE", "") or "").rstrip("/")
        if base:
            try:
                resp = httpx.get(f"{base}/health", timeout=5.0)
                if resp.status_code >= 400:
                    problems.append(f"embedding 服务异常 HTTP {resp.status_code}：{base}")
            except Exception as exc:  # noqa: BLE001
                hint = ""
                if any(
                    os.environ.get(k)
                    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
                ):
                    hint = "（检测到本机设了 HTTP(S)_PROXY；已自动排除 localhost，若仍失败请检查代理配置）"
                problems.append(f"embedding 服务不可达：{base}（{type(exc).__name__}）{hint}")
    return problems


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
    failure_reason: list[str] = field(default_factory=list)
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
    # paired control：本 case 是否开着 Store（False=对照组）
    store_enabled: bool = True

    # —— 派生（仅供调试，不进报告）——
    retrieval_ok: bool = False
    retrieval_status: str = ""
    retrieval_error: str = ""
    env_error: bool = False  # ★ 环境类错误（额度/鉴权）——必须从失败归因中剔除

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
        data = self.__dict__.copy()
        data["memory_correct_use"] = self.memory_correct_use
        return data

    @property
    def memory_correct_use(self) -> bool | None:
        """主指标：`retrieved ∧ used ∧ correct`（§2.B.4）。三者有 None → None。"""
        trio = (self.memory_retrieved, self.memory_used, self.memory_correct)
        if any(v is None for v in trio):
            return None
        return all(bool(v) for v in trio)


# ── 机械判定 ──────────────────────────────────────────────


def generation_ok(task: str, reply: str, hard_fails: list[str]) -> bool:
    """「有没有产出**合法结果**」—— 与质量无关（§2.B.3 ②）。"""
    if hard_fails or not reply.strip():
        return False
    if task in ("qa", "verify"):
        return True
    if task == "generate":
        return bool(_GEN_REQUIRED_MARKERS.search(reply))
    if task == "grade":
        return bool(_GRADE_FIELD_RE.search(reply))
    if task == "memory":
        return True
    return False


def mechanical_failures(
    task: str, probe: RetrievalProbe, reply: str, hard_fails: list[str]
) -> list[str]:
    """只在**机械可判**的范围内收集 failure_reason；生成质量类留给 judge。

    ★ `memory` 豁免检索判据（2026-10-05 修）：Memory 的 query（「我是 2027 考研…」）
      本就不是知识查询，检索返空属**预期**。若照记 `retrieval_miss`，
      Phase 1 会误判「记忆差是因为检索差」—— 归因方向直接错。
      Memory 的判据是三维 `retrieved ∧ used ∧ correct`。
    """
    reasons: list[str] = []
    if any("invoke 抛错" in h or "工具" in h for h in hard_fails):
        reasons.append("tool_error")
    if probe.status == "error":
        reasons.append("tool_error")
    if task != "memory" and not probe.ok:
        reasons.append("retrieval_miss")
    if not reply.strip():
        reasons.append("generation_incomplete")
    return reasons


# ── 执行 ──────────────────────────────────────────────────


async def _run_agent(
    turns: list[str],
    *,
    task: str = "",
    case_id: str = "",
    sessions: list[list[str]] | None = None,
    store_enabled: bool = True,
):
    """跑真实 agent。惰性导入 `scripts/` 下的 smoke 封装（与 gate 同一套调用链）。

    ★★ **必须自行装配 checkpointer / store**（2026-10-05 实测教训）：
    服务端是在 FastAPI lifespan 里挂的（`service.py:129` `agent.checkpointer = saver`），
    而 `run_turns` 只调 `get_agent()`、**从不挂**。不挂的后果是**多轮之间没有历史** ——
    实测第 2 轮追问「我叫什么」，系统答「我这边暂时没有你的个人信息记录」。

    这会让 Memory 任务的测量**完全失真**（测的是「无 checkpointer 的 agent」，
    不是产品）。故此处逐字对齐 `service.lifespan` 的装配方式。

    ★ **memory 任务走 `run_sessions`**（2026-10-06 修，Step 4 接线）：
      Memory 要测的是**跨会话**长期记忆（Store），而不是**会话内**多轮（checkpointer）。
      二者的差别不是措辞 —— 若 memory 也走 `run_turns`（单 thread 跑完全部轮次），
      则「第 2 轮记得第 1 轮的话」完全可由 checkpointer 解释，**证明不了 Store 起了作用**。

      `run_sessions` 把每段会话拆成**独立 thread**（各自新会话）、共享同一 `user_id`，
      并在跑前跑后清理 Store / checkpointer ⇒ 唯一能连通两段的只有 Store，
      同时产出 `memory_cards`（机械判定 `recalled` 的证据）。

      ★ **会话分组由 `case.all_sessions` 决定**（2026-10-06 补）：
        - 有 `sessions` 字段 ⇒ 按标注的段数拆 thread（真跨会话）；
        - 无 `sessions` ⇒ 退化为「每轮一段」（`[[t] for t in turns]`）。
        这里的 `sessions` 由 `run_case` 从 `case.all_sessions` 传入，**不在本函数里重算** ——
        避免「解析处」与「执行处」两套分组逻辑漂移。

      `user_id` **每条 case 独立**（`make_user_id(case_id)`，带随机后缀）⇒
      case 之间与重跑之间都天然隔离，不会互相污染。
    """
    scripts_dir = ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))

    from agent_behavior_smoke import (  # type: ignore[import-not-found]
        make_user_id,
        run_sessions,
        run_turns,
    )

    from agents.agents import DEFAULT_AGENT, get_agent
    from memory import initialize_database, initialize_store
    from memory.runtime import set_store

    async with initialize_database() as saver, initialize_store() as store:
        if hasattr(saver, "setup"):
            await saver.setup()
        set_store(store)
        agent = get_agent(DEFAULT_AGENT)
        agent.checkpointer = saver
        agent.store = store
        if task == "memory":
            # ★ 跨会话：每段会话独立 thread、共享 user_id、跑前跑后自动清理。
            #   分组以传入的 sessions 为准；未标注时退化为「每轮一段」。
            eff_sessions = sessions if sessions else ([[t] for t in turns] if turns else [])
            return await run_sessions(
                agent,
                eff_sessions,
                user_id=make_user_id(case_id or "memory"),
                cleanup_first=True,
                store_enabled=store_enabled,
            )
        return await run_turns(agent, turns)


def _tool_call_summaries(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in payloads:
        out.append(
            {
                "kind": "search" if p.get("query") is not None else "other",
                "status": p.get("status", ""),
                "query": str(p.get("query") or "")[:80],
                "docs": len(p.get("docs") or []),
            }
        )
    return out


def _apply_memory_judgement(
    record: CaseRecord,
    case: TaskCase,
    memory_cards: list[str],
    reply: str,
) -> list[str]:
    """**机械判定** Memory 三维并写入 record；返回需追加的 failure_reason。

    ★ 只在 case validity **通过**时调用（前置条件不成立时三项应保持 N/A）。
    ★ 必须在 judge 之前算：judge 的 `apply_judge` 已加护栏**不再写**这三项，
      若这里不算，record 的 memory_* 将恒为 None ⇒ 主指标全 N/A。
    """
    _m = memory_scorer.judge_memory_mechanically(
        memory_cards=memory_cards,
        reply=reply,
        gold=case.gold,
    )
    record.memory_retrieved = _m.recalled_pass  # ★ 进主指标的是「与期望对齐」的结果
    record.memory_recalled_actual = _m.recalled_actual
    record.memory_used = _m.used
    record.memory_correct = _m.correct
    record.memory_hit_values = list(_m.hit_values)
    record.memory_forbidden_hits = list(_m.forbidden_hits)
    record.memory_cards = memory_cards
    # ★ gold 未标注/非法 ⇒ 三项记 None（N/A，不进分母），并标 `memory_miss`
    #   提示人工补齐。**绝不**回退 judge 猜测（那正是本轮要消除的问题）。
    extra: list[str] = []
    if not case.gold.memory_mechanizable() and "memory_miss" not in record.failure_reason:
        extra.append("memory_miss")
    return extra


async def run_case(
    case: TaskCase,
    *,
    k: int = 5,
    use_rerank: bool = True,
    run_agent: bool = True,
    store_enabled: bool = True,
) -> CaseRecord:
    """执行一条 case。`run_agent=False` 时只跑检索探针（离线/无 LLM 时可用）。

    `store_enabled`：**paired control**（2026-10-06 Step 5）——仅对 memory 生效。
      `False` ⇒ 临时摘除 agent.store，B 段不应有任何记忆卡 ⇒ `recalled_actual=False`。
      与 `True` 组配对，可把「召回确实来自 Store」从推断变成**机械对照**。
    """
    started = time.perf_counter()
    record = CaseRecord(
        case_id=case.case_id,
        task=case.task,
        task_mode=case.task_mode,
        query=case.query,
        turns=case.all_turns,
        gold_status=case.gold_status,
    )

    reply = ""
    hard_fails: list[str] = []
    payloads: list[dict[str, Any]] = []
    memory_cards: list[str] = []
    grade_scores: list[dict[str, Any]] = []
    if run_agent:
        try:
            result = await _run_agent(
                case.all_turns,
                task=case.task,
                case_id=case.case_id,
                sessions=case.all_sessions if case.task == "memory" else None,
                store_enabled=store_enabled,
            )
            reply = result.reply
            hard_fails = list(result.hard_fails)
            payloads = list(result.tool_payloads)
            memory_cards = list(getattr(result, "memory_cards", []) or [])
            grade_scores = list(getattr(result, "grade_scores", []) or [])
        except Exception as e:  # noqa: BLE001
            logger.warning("case %s agent 执行失败: %s", case.case_id, e)
            hard_fails.append(f"invoke 抛错: {type(e).__name__}: {e}")

    probe = await probe_retrieval(
        case.query, task_mode=case.task_mode or None, k=k, use_rerank=use_rerank
    )

    record.reply = reply
    record.hard_fails = hard_fails
    record.gold = asdict(case.gold)
    record.tool_calls = _tool_call_summaries(payloads)
    record.pack_nonempty = probe.ok
    record.pack_len = probe.pack_len
    record.evidence_count = probe.evidence_count
    record.retrieval_ok = probe.ok
    record.retrieval_status = probe.status
    record.retrieval_error = probe.error

    top = probe.top_k(k)
    # ★ 2026-10-06 修：**检索到的 chunk 没有任何 KP 元数据时，`kp_hit` 记 N/A 而非 False** ——
    #   此时「覆盖与否」不可判定，记 False 会变成**系统性假阴性**（把 0.714 压成 0.333，
    #   直接误导 Phase 1 的投入方向）。`metrics.rate` 排除 None，故 N/A 不进分母。
    #   ★ 2026-10-07 全量扫描更正缺口的**范围**（原注释说「`basic/`、`advanced/` 集合缺标签」，
    #     方向对但说大了）：真正无 `knowledge_points` 的是 **`doc_role=textbook`（basic 讲义）的
    #     `detail` 块**，且当前只剩 **10 条**（`data_structure` 8 / `computer_organization` 2）——
    #     四个学科集合的覆盖率为 **99.0% / 99.6% / 100% / 100%**。
    #     另有 `questions` 集合 692 条无标签块（`exam-*-answer` 真题答案），但 **practice 模式的
    #     可用层是 `["advanced","basic"]`**（`schema/task_policy.py` 还强制 practice 的
    #     `exam_resources` 全 forbidden）⇒ 那些块不进证据包，与本判据无关。
    #   ⇒ 归档里 Generate 那 **8 条 N/A** 最可能是**当时索引未打完标签**的产物（现索引下
    #     裸向量重查 15/15 的 top-5 均带 KP），但**记录未保存每块来源/标签**，无法证明；
    #     只能由 Step 9 走完整管线实跑定论。见 `docs/EXPERIMENTS.md` §20.5.1。
    _retrieved_kp = _all_kp(top)
    record.kp_hit = (
        metrics.kp_coverage(case.gold.expected_kp, _retrieved_kp) if _retrieved_kp else None
    )
    record.kp_mrr = metrics.kp_mrr(case.gold.expected_kp, [i.knowledge_points for i in top])
    record.category_hit = metrics.category_hit(case.subject, [i.category for i in top])
    record.exam_hit = metrics.exam_hit_at_k([i.is_exam for i in top], k)

    record.generation_ok = generation_ok(case.task, reply, hard_fails)
    # ── Generate 交付五项（机械判据 + 既有 judge 质量分，**不需额外 LLM 调用**）──
    if case.task == "generate":
        record.gen_structure = metrics.structure_pass(reply)
        record.gen_answerability = metrics.answerability_pass(reply)
        record.gen_coverage = record.kp_hit  # 无可靠 expected_kp 时 kp_hit 已是 None
        # `gen_correctness`（内容正确率）**不在这里算** —— 它依赖 `final_quality`，
        # 而 judge 在本函数返回之后才跑。归属见 `judge._sync_generate_correctness`
        # （谁写 final_quality，谁刷新派生指标）。此处保持 None。
        # 难度匹配：expected_difficulty 无可靠 gold（黄金集无难度字段、query 未指定）
        # ⇒ 本批一律 N/A。**不编默认值、不用系统自报的「理解/综合」反推 gold**
        #   （用户 2026-10-06 裁决）⇒ 第二个入参恒为 None，`difficulty_match` 必返 None。
        record.gen_difficulty = metrics.difficulty_match(case.gold.expected_difficulty, None)
    record.failure_reason = mechanical_failures(case.task, probe, reply, hard_fails)
    # ── Memory：**先验 case validity，再判三维**（2026-10-06 Step 5）────────
    #   ★ 顺序不可颠倒：若 A 段没凑成前置条件（如要求两次高分、实际 100/52），
    #     则 B 段「没召回」是**前置条件没成立**的结果，不是产品失败。
    #     先判 validity 才能把这类样本从分母里剔掉 —— 否则 grading LLM 的随机性
    #     会污染 Memory 指标（把「case 没凑成」记成「产品不召回」）。
    if case.task == "memory":
        _validity = memory_scorer.check_case_validity(
            setup=case.gold.setup_conditions,
            grade_scores=grade_scores,
            session_scope=0,  # 前置条件归 A 段
        )
        record.validity_valid = _validity.valid
        record.validity_reason = _validity.reason
        record.grade_scores = grade_scores
        record.store_enabled = store_enabled

        if _validity.valid is False:
            # 前置条件不成立 ⇒ Memory 三项**保持 None**（N/A，不进分母），
            #   并标 `case_invalid`（**不**标 memory_miss —— 那会被读成「产品没召回」）。
            record.memory_cards = memory_cards
            if "case_invalid" not in record.failure_reason:
                record.failure_reason = [*record.failure_reason, "case_invalid"]
        else:
            record.failure_reason = [
                *record.failure_reason,
                *_apply_memory_judgement(record, case, memory_cards, reply),
            ]
    # ★ 环境类错误优先判定：命中则**不**把它计入 case 级 failure_reason，
    #   由调用方中止整轮（见 cli._run），避免「账号没额度」被记成「工具报错」。
    record.env_error = is_env_error(" ".join(hard_fails) + " " + probe.error)
    if record.env_error:
        record.failure_reason = ["tool_error"]
        record.primary_failure = "tool_error"
    else:
        record.primary_failure = metrics.pick_primary_failure(record.failure_reason)

    from core.settings import settings as _settings
    from evaluation.provenance import build_provenance

    prov = build_provenance("evaluation.task_eval.runner")
    # ★ 2026-10-06 修：`build_provenance()` 把 `code_version` 放在**嵌套的 `provenance`** 里，
    #   而原实现从**顶层**取 `prov.get("code_version")` ⇒ 永远取到 None ⇒
    #   归档里的 `code_version` **一直是空字符串**，导致「冻结快照 ↔ 代码版本」无法对应
    #   （冻结一致性检查第 1 项直接失败）。
    _inner = prov.get("provenance") or {}
    record.code_version = str(_inner.get("code_version") or "")
    record.golden_sha256 = str(_inner.get("golden_sha256") or "")
    # ★ 修 #3：`-dirty` 区分不了一次改造里的多轮 ⇒ 直接把提示词内容 hash 落到每条 record
    from prompts import PROMPT_SET_VERSION

    record.prompt_set_version = str(PROMPT_SET_VERSION)
    record.date = str(prov.get("recorded_at") or "")
    record.agent_model = str(getattr(_settings, "DEFAULT_MODEL", "") or "")
    record.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return record


def _all_kp(items) -> list[str]:
    out: list[str] = []
    for it in items:
        out.extend(it.knowledge_points)
    return out


def write_jsonl(path: str | Path, rows: list[dict]) -> Path:
    """整体重写 jsonl（dict 行）。**每行都以 `\\n` 结尾，包括最后一行。**

    ★ 为什么收成一处（2026-10-07）：`cli.py` 的三处写出原先各自用
      `write_text("\\n".join(...))` —— 该写法**不留尾换行**，而 `append_record`
      是 `"a"` 模式追加 `json + "\\n"`。两者相遇时新记录会**粘在末行尾部**，
      拼成一条解析失败的坏行 ⇒ **上一条与这一条同时丢失**（实测：3 条只剩 1 条可读）。
      后果不只丢数据：`load_done_ids` 读不到被粘住的 case_id ⇒ 续跑会**重做**它，
      而那条已经烧过的 token 无从追溯。
      行格式现在只有一份实现，新调用方不可能再漏掉尾换行。
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def _needs_newline_pad(path: Path) -> bool:
    """文件存在、非空、且末字节不是 `\\n` ⇒ True（需要补分隔符才能安全追加）。"""
    try:
        size = path.stat().st_size
        if not size:
            return False
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) != b"\n"
    except OSError:
        return False


def dump_records(records: list[CaseRecord], path: str | Path) -> Path:
    """把 record 列表落盘为 jsonl（供报告与论文复算）。"""
    out = write_jsonl(path, [r.to_dict() for r in records])
    logger.info("写入 %d 条 record → %s", len(records), out)
    return out


def append_record(record: CaseRecord, path: str | Path) -> None:
    """**逐条追加**一条 record 并立即 flush。

    ★ 为什么必须有（2026-10-05 实测教训）：原实现只在整轮结束时 `dump_records`，
      于是一次跑满 15 分钟、发出 **165 次 LLM 调用**的 run 被中止后，
      **一条记录都没落盘** —— 配额全白烧。逐条追加让「跑一半被中止」不再丢数据，
      配合 `load_done_ids` 可**续跑**。
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if _needs_newline_pad(out):
        # 见 `write_jsonl` 的说明：末行缺尾换行时直接 append 会把两条粘成一条坏行。
        logger.warning("目标 jsonl 末行无换行，追加前先补一个 —— %s", out)
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n")
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        f.flush()


def load_done_ids(path: str | Path) -> set[str]:
    """读出**真正完成**的 case_id（用于续跑时跳过）。

    ★ 环境错误的记录**不算完成**（2026-10-05 修）：欠费/额度耗尽时写下的 record
      是「没跑成」，若也计入 done，续跑会把它**永久跳过** —— 实测 mem-006
      因欠费失败后被误判「已完成」，补跑时被跳过。
      故这里只认「非环境错误」的记录，让环境恢复后能自动补跑。
    """
    out = Path(path)
    if not out.exists():
        return set()
    done: set[str] = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # 被中断写坏的最后一行：忽略即可，续跑会重做该 case
        text = " ".join(obj.get("hard_fails") or []) + " " + str(obj.get("retrieval_error") or "")
        if is_env_error(text):
            continue  # 环境错误 → 视为未完成，允许重试
        case_id = str(obj.get("case_id") or "")
        if case_id:
            done.add(case_id)
    return done
