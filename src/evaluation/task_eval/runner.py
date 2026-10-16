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

import logging
import time
from dataclasses import asdict
from typing import Any

from evaluation.task_eval import memory_scorer, metrics
from evaluation.task_eval._runner_agent import (
    _apply_memory_judgement,
    _run_agent,
    _tool_call_summaries,
    aggregate_memory_read_status,
)
from evaluation.task_eval._runner_record import CaseRecord
from evaluation.task_eval._runner_support import (  # noqa: F401  兼容消费方从 runner 取这些名
    _all_kp,
    append_record,
    dump_records,
    generation_ok,
    is_env_error,
    load_done_ids,
    map_route_failures,
    mechanical_failures,
    memory_write_missing,
    preflight_check,
    write_jsonl,
)
from evaluation.task_eval.cases import TaskCase
from evaluation.task_eval.retrieval_probe import probe_retrieval

logger = logging.getLogger(__name__)

# ── 机械判定 ──────────────────────────────────────────────


# ── 执行 ──────────────────────────────────────────────────


async def _execute_agent_case(
    case: TaskCase, *, run_agent: bool, store_enabled: bool
) -> dict[str, Any]:
    """跑 agent 并收集产物，外加本轮的读链状态明细。

    返回 ``reply / hard_fails / payloads / memory_cards / grade_scores / turn_log /
    episodes / episodes_read_failed / read_status_detail``。

    ★ B4 取证单元 ②的「清空」半边：本 case 的读链状态从这里开始收集（`load_memory` 每轮往
      `agents.teaching_graph` 的模块级通道追加一条）。不 reset 就是「上一条 case 的 Store
      故障一路跟着这一条」—— 与 `_query_failures` 同一个失效模式，见
      `vectorstore.reset_query_failures` 的**两个单元边界**。
    """
    from agents.teaching_graph import memory_read_statuses, reset_memory_read_statuses

    reset_memory_read_statuses()
    out: dict[str, Any] = {
        "reply": "",
        "hard_fails": [],
        "payloads": [],
        "memory_cards": [],
        "grade_scores": [],
        "turn_log": [],
        "episodes": [],
        "episodes_read_failed": False,
        "read_status_detail": [],
    }
    if run_agent:
        try:
            result = await _run_agent(
                case.all_turns,
                task=case.task,
                case_id=case.case_id,
                sessions=case.all_sessions if case.task == "memory" else None,
                store_enabled=store_enabled,
            )
            out["reply"] = result.reply
            out["hard_fails"] = list(result.hard_fails)
            out["payloads"] = list(result.tool_payloads)
            out["memory_cards"] = list(getattr(result, "memory_cards", []) or [])
            out["grade_scores"] = list(getattr(result, "grade_scores", []) or [])
            out["turn_log"] = list(getattr(result, "turn_log", []) or [])
            out["episodes"] = list(getattr(result, "episodes", []) or [])
            out["episodes_read_failed"] = bool(getattr(result, "episodes_read_failed", False))
        except Exception as e:  # noqa: BLE001
            logger.warning("case %s agent 执行失败: %s", case.case_id, e)
            out["hard_fails"].append(f"invoke 抛错: {type(e).__name__}: {e}")
    out["read_status_detail"] = memory_read_statuses() if run_agent else []
    return out


def _write_agent_fields(record: CaseRecord, case: TaskCase, agent_out: dict[str, Any]) -> None:
    """落盘 agent 侧字段 + B4/F5 读链状态（逐轮明细 + 聚合值）。"""
    record.reply = agent_out["reply"]
    record.hard_fails = agent_out["hard_fails"]
    record.gold = asdict(case.gold)
    record.tool_calls = _tool_call_summaries(agent_out["payloads"])
    # ★ B4：把本轮捕获到的读链状态聚合成**一个** `memory_read_status` 落盘（四态无损）。
    # ★ F5：聚合**之前**的逐轮明细先原样落盘（`memory_read_statuses`）—— 聚合规则第 1 条
    #   「有卡 ⇒ success」压掉的 `failed` 只有在这份明细里才还看得见。明细只作凭据、不进公式。
    record.memory_read_statuses = list(agent_out["read_status_detail"])
    record.memory_read_status = aggregate_memory_read_status(
        agent_out["read_status_detail"], agent_out["memory_cards"]
    )


async def _run_probe(case: TaskCase, *, k: int, use_rerank: bool):
    """B7：reset → 跑检索探针 → 读回路由失败并归状态（只升不降）。"""
    from rag.common.vectorstore import get_vector_store_manager

    # ★ B7 的 reset 调用点 ②（两个独立取证单元边界之一）：每次检索探针之前清空
    #   ⇒ 探针期间记录的查询故障**只属于这次探针**，紧接着在下面被消费。
    #   顺序不可颠倒（reset 早于消费）也不许在单元内部再加清点（v1.3 撤销了第三点，
    #   见 `rag/routes._amulti_route_search` 的注释与回归锁 `8k`）。
    mgr = get_vector_store_manager()
    mgr.reset_query_failures()
    probe = await probe_retrieval(
        case.query, task_mode=case.task_mode or None, k=k, use_rerank=use_rerank
    )
    # ★ B7 消费侧（v1.3 裁定 R4）：路由的失败在这里被读回状态。
    #   `_safe_to_thread` 按路由逐个收敛 ⇒ 探针**收不到异常**、自报 `ok`/`empty`（实测注入
    #   BM25 全线故障：`status='ok' pack_len=755`）⇒ 只看探针会把「路由坏了」写成「没查到」。
    #   非空清单 ⇒ 升为 `error`（只升不降，纯函数 `map_route_failures`），清单落 `route_failure_notes`
    #   作凭据；归因门复用 `judge.retrieval_layer_gate_open`（`error` ⇒ 关门，不另写一份规则）。
    effective_status, route_failure_notes = map_route_failures(mgr.query_failures, probe.status)
    return probe, effective_status, route_failure_notes


def _write_retrieval_fields(
    record: CaseRecord,
    probe,
    top,
    *,
    k: int,
    use_rerank: bool,
    effective_status: str,
    route_failure_notes: list[str],
) -> None:
    """落盘检索探针侧字段 + `retrieval_cfg` + `top_items`。"""
    record.pack_nonempty = probe.ok
    record.pack_len = probe.pack_len
    record.evidence_count = probe.evidence_count
    record.retrieval_ok = probe.ok
    record.retrieval_status = effective_status
    record.route_failure_notes = route_failure_notes
    record.retrieval_error = probe.error
    # ★ B2：把检索探针的 tier-0 重排状态落进 record（含 `--no-agent` 的探针归档）。
    #   `rerank_used` 不在这里存布尔 —— 它由 CaseRecord 的派生 property（status=="success"）给出。
    #   缺字段（替身/老链路探针）⇒ ""（未知），与「不回填」纪律一致。
    record.rerank_status = getattr(probe, "rerank_status", "")
    # ★ 落盘「配置 + top-k 输入」，让检索侧指标可离线重算（字段说明见 CaseRecord）
    from core.settings import settings as _prov

    record.retrieval_cfg = {
        "k": k,
        "use_rerank_requested": use_rerank,
        "rerank_effective": bool(_prov.RERANK_ENABLED) and bool(use_rerank),
        "use_fake_embedding": bool(_prov.USE_FAKE_EMBEDDING),
        "semantic_cache_enabled": bool(_prov.SEMANTIC_CACHE_ENABLED),
    }
    record.top_items = [
        {
            "source": i.source,
            "category": i.category,
            "doc_role": i.doc_role,
            "kb_depth": i.kb_depth,
            "kp": list(i.knowledge_points),
            "score": round(i.score, 4),
        }
        for i in top
    ]


def _write_retrieval_metrics(record: CaseRecord, case: TaskCase, top, k: int) -> None:
    """落盘检索侧指标（kp / category / exam）。

    ★ 2026-10-06 修：**检索到的 chunk 没有任何 KP 元数据时，`kp_hit` 记 N/A 而非 False** ——
      此时「覆盖与否」不可判定，记 False 会变成**系统性假阴性**（把 0.714 压成 0.333，
      直接误导 Phase 1 的投入方向）。`metrics.rate` 排除 None，故 N/A 不进分母。
    ★ 2026-10-07 全量扫描更正缺口的**范围**（原注释说「`basic/`、`advanced/` 集合缺标签」，
      方向对但说大了）：真正无 `knowledge_points` 的是 **`doc_role=textbook`（basic 讲义）的
      `detail` 块**，且当前只剩 **10 条**（`data_structure` 8 / `computer_organization` 2）——
      四个学科集合的覆盖率为 **99.0% / 99.6% / 100% / 100%**。
      另有 `questions` 集合 692 条无标签块（`exam-*-answer` 真题答案），但 **practice 模式的
      可用层是 `["advanced","basic"]`**（`schema/task_policy.py` 还强制 practice 的
      `exam_resources` 全 forbidden）⇒ 那些块不进证据包，与本判据无关。
    ⇒ 归档里 Generate 那 **8 条 N/A** 曾有两条候选解释，都**不能定论**（记录没存
      `evidence_id` ⇒ 分不清某块走的是哪条路径）：
        ① 旧说「当时索引未打完标签」—— 现索引下裸向量重查 15/15 的 top-5 均带 KP；
        ② 新说 **#27**：`rag/layer_recall.py` 的 top-up 路径把 `knowledge_points`
           **写死成 `[]`**（主路径 `rag/evidence.py` 是用解析器读的）⇒ 某题 top-5
           若全走 top-up，`_all_kp(top)` 就是空 ⇒ 判 N/A，与索引有没有标签无关。
      ② 有按构造的实证，且能解释 Step 9 探针归档里 13 条「索引明明有标、`kp` 却为空」
      的 method 块 ⇒ 比 ① 更可能。处置见 `docs/EXPERIMENTS.md` §20.5 #27 / D12。
    """
    _retrieved_kp = _all_kp(top)
    record.kp_hit = (
        metrics.kp_coverage(case.gold.expected_kp, _retrieved_kp) if _retrieved_kp else None
    )
    record.kp_mrr = metrics.kp_mrr(case.gold.expected_kp, [i.knowledge_points for i in top])
    record.category_hit = metrics.category_hit(case.subject, [i.category for i in top])
    record.exam_hit = metrics.exam_hit_at_k([i.is_exam for i in top], k)


def _write_scoring_fields(
    record: CaseRecord,
    case: TaskCase,
    probe,
    *,
    reply: str,
    hard_fails: list[str],
    effective_status: str,
) -> None:
    """落盘 `generation_ok` + Generate 交付项 + `failure_reason` + Verify 行为层三判据。"""
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
    record.failure_reason = mechanical_failures(
        case.task, probe, reply, hard_fails, retrieval_status=effective_status
    )
    # ── Verify 行为层三判据（D14，2026-10-08）────────────────────────────
    #   ★ 2026-10-15 owner 裁定 B2 第三路（改 backfill 落盘口径）：这三个字段曾有
    #     **两个写入方、极性相反** —— runner 直写 metric 极性（`verify_fabricated`
    #     返 True = 仍出题 = 坏事）vs backfill 按 registry 落 verdict 极性
    #     （`to_record_value("pass") = True` = 好事）。实测后果：ec 代归档
    #     `ver_fabricated=True×15` 被 `report` 按 metric 极性读成「编造率 1.000」
    #     的**假红**（registry 重算实情：pass 15/15、编造率 0）。
    #     root fix = 两个写入方统一走 **registry 判据**（公式仍只有 registry 一处），
    #     并按 protocol 同写 `item_reasons` 标记 ⇒ 读取方凭标记无歧义解码
    #     （`report._fabrication_flag`；ec 代归档 vs phase1 代归档不再混读）。
    #     registry 判据自带「无回复/缺检索状态 ⇒ missing_premise ⇒ None」纪律，
    #     取代原来的 `reply.strip()` 前置守卫（没测 ≠ 没出题）。
    if case.task == "verify":
        from evaluation.task_eval.predicates import common as pc
        from evaluation.task_eval.predicates import registry

        for pred in registry.for_task("verify"):
            v = pred.fn(record.to_dict())
            setattr(record, pred.name, pc.to_record_value(v))
            record.item_reasons[pred.name] = "" if v in ("pass", "fail") else v


def _apply_write_missing_gate(
    record: CaseRecord,
    validity,
    grade_scores: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    episodes_read_failed: bool,
    store_enabled: bool,
) -> bool:
    """写入证据缺失 ⇒ 把 validity 降为 False（**未归因**）；返回最终 validity 值。

    ★ 写入证据缺失（2026-10-07 事故驱动；2026-10-08 review 修正**位置**与**归因**）
      ① 位置：必须在 `case.task == "memory"` **之内**。非 memory 任务走 `run_turns`，
         它照抓 `grade_scores`、却从不读 Store ⇒ `episodes` 恒空；放外面等于宣布
         「所有批改类 case 天生写链断裂」⇒ grade/verify/qa 的实跑会在**第一条**就
         被 `cli._run` 中止（且 `break` 在 `append_record` 之前，那条记录连盘都不落）。
      ② 归因：**只说「证据缺失」，不指认环境。** 「没落库」既可能是 TEI 挂（环境），
         也可能是缺陷 C 那种 `record_grade` 接线断（产品）—— 两者症状相同，而
         `memory/safe.py` 只留一行 WARNING。环境类另有两道真判据：`preflight_check()`
         与 `is_env_error()`（看真实报错文本）。
      ③ 读链自己抛过错时（`episodes_read_failed`）不做任何写入推断。
    """
    record.memory_write_missing = memory_write_missing(
        store_enabled=store_enabled,
        grade_calls=sum(1 for g in grade_scores if g.get("score") is not None),
        episodes=episodes,
        read_failed=episodes_read_failed,
    )
    _valid = validity.valid
    if record.memory_write_missing and _valid is not False:
        _valid = False
        record.validity_reason = (
            (f"{validity.reason}；" if validity.reason else "")
            + "A 段有批改、Store 开着却没读到 episode ⇒ 记忆写入证据缺失（**未归因**），本条不进 Memory 分母"
        )
    record.validity_valid = _valid
    return _valid


def _write_memory_fields(
    record: CaseRecord,
    case: TaskCase,
    agent_out: dict[str, Any],
    *,
    store_enabled: bool,
    reply: str,
) -> None:
    """Memory 专有：**先验 case validity，再判三维**（2026-10-06 Step 5）。

    ★ 顺序不可颠倒：若 A 段没凑成前置条件（如要求两次高分、实际 100/52），
      则 B 段「没召回」是**前置条件没成立**的结果，不是产品失败。
      先判 validity 才能把这类样本从分母里剔掉 —— 否则 grading LLM 的随机性
      会污染 Memory 指标（把「case 没凑成」记成「产品不召回」）。
    """
    memory_cards = agent_out["memory_cards"]
    grade_scores = agent_out["grade_scores"]
    episodes = agent_out["episodes"]
    episodes_read_failed = agent_out["episodes_read_failed"]

    _validity = memory_scorer.check_case_validity(
        setup=case.gold.setup_conditions,
        grade_scores=grade_scores,
        session_scope=0,  # 前置条件归 A 段
    )
    record.validity_valid = _validity.valid
    record.validity_reason = _validity.reason
    record.grade_scores = grade_scores
    record.turn_log = agent_out["turn_log"]
    record.episodes = episodes
    record.episodes_read_failed = episodes_read_failed
    record.store_enabled = store_enabled

    _valid = _apply_write_missing_gate(
        record, _validity, grade_scores, episodes, episodes_read_failed, store_enabled
    )

    if _valid is False:
        # 前置条件不成立（或写入证据缺失）⇒ Memory 三项**保持 None**（N/A，不进分母），
        #   并标 `case_invalid`（**不**标 memory_miss —— 那会被读成「产品没召回」）。
        record.memory_cards = memory_cards
        if "case_invalid" not in record.failure_reason:
            record.failure_reason = [*record.failure_reason, "case_invalid"]
    else:
        record.failure_reason = [
            *record.failure_reason,
            *_apply_memory_judgement(record, case, memory_cards, reply),
        ]


def _write_env_and_provenance(record: CaseRecord, probe, started: float) -> None:
    """环境类错误判定 + `primary_failure` + provenance / 模型 / 延迟落盘。"""
    # ★ 环境类错误优先判定：命中则**不**把它计入 case 级 failure_reason，
    #   由调用方中止整轮（见 cli._run），避免「账号没额度」被记成「工具报错」。
    record.env_error = is_env_error(" ".join(record.hard_fails) + " " + probe.error)
    if record.env_error and not (record.hard_fails or record.retrieval_error):
        # 中止日志从 `hard_fails[0]` / `retrieval_error` 取文案；两者都空时那行会打成**空串**
        # （review C1 的姊妹问题：运维看到的是一句没有原因的「中止」）。兜一句可操作的话。
        record.hard_fails = [
            *record.hard_fails,
            "环境类错误（由 is_env_error 判据命中，未捕获到原始报错文本）",
        ]

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
    # ★ 主从关系：上面的标量仍是现有消费者（report/reprobe/freeze_precheck）的权威，
    #   record.provenance 是完整证据副本；两者必须来自**同一次** build_provenance() 调用。
    record.provenance = dict(_inner)
    # ★ 修 #3：`-dirty` 区分不了一次改造里的多轮 ⇒ 直接把提示词内容 hash 落到每条 record
    from prompts import PROMPT_SET_VERSION

    record.prompt_set_version = str(PROMPT_SET_VERSION)
    record.date = str(prov.get("recorded_at") or "")
    record.agent_model = str(getattr(_settings, "DEFAULT_MODEL", "") or "")
    record.latency_ms = round((time.perf_counter() - started) * 1000, 3)


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

    agent_out = await _execute_agent_case(case, run_agent=run_agent, store_enabled=store_enabled)
    _write_agent_fields(record, case, agent_out)

    probe, effective_status, route_failure_notes = await _run_probe(
        case, k=k, use_rerank=use_rerank
    )
    top = probe.top_k(k)
    _write_retrieval_fields(
        record,
        probe,
        top,
        k=k,
        use_rerank=use_rerank,
        effective_status=effective_status,
        route_failure_notes=route_failure_notes,
    )
    _write_retrieval_metrics(record, case, top, k)
    _write_scoring_fields(
        record,
        case,
        probe,
        reply=agent_out["reply"],
        hard_fails=agent_out["hard_fails"],
        effective_status=effective_status,
    )
    if case.task == "memory":
        _write_memory_fields(
            record, case, agent_out, store_enabled=store_enabled, reply=agent_out["reply"]
        )
    _write_env_and_provenance(record, probe, started)
    return record
