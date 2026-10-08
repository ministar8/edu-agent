"""task_eval CLI：Phase 0 的入口（run / calibrate）。

    PYTHONPATH=src uv run python -m evaluation.task_eval run --limit 3
    PYTHONPATH=src uv run python -m evaluation.task_eval run --task verify --no-judge
    PYTHONPATH=src uv run python -m evaluation.task_eval calibrate --input evals/datasets/demo/_calibration.jsonl

★ 默认**不写论文归档**：`--out` 不给就只打印报告。归档请显式指定
  `evals/results/task_eval/phase0_<date>.jsonl`。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from core.settings import settings
from evaluation.task_eval import judge as judge_mod
from evaluation.task_eval.cases import TASKS, load_demo
from evaluation.task_eval.report import build_report, render_markdown
from evaluation.task_eval.runner import (
    append_record,
    load_done_ids,
    preflight_check,
    run_case,
    write_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("task_eval")


async def _run(args: argparse.Namespace) -> int:
    cases = load_demo(args.task, limit=args.limit, demo_dir=getattr(args, "demo_dir", None))
    if not cases:
        logger.error("没有加载到 case —— 先建 evals/datasets/demo/（见 README.md）")
        return 2
    logger.info("加载 %d 条 case（tasks=%s, limit=%s）", len(cases), args.task or "all", args.limit)

    # ★ 运行前预检：外部服务挂了就别开跑（实测：TEI 停了会烧满 12 分钟且产出假数据）
    problems = preflight_check()
    if problems:
        for p in problems:
            logger.error("预检失败：%s", p)
        print(
            "\n> ⛔ **运行前预检失败，已中止（未消耗任何 LLM 调用）**：\n"
            + "\n".join(f">   - {p}" for p in problems)
            + "\n> 请先恢复依赖服务（如 `docker compose up -d tei`），再重跑。\n"
        )
        return 3

    records = []
    env_blocked = 0
    done = load_done_ids(args.out) if (args.out and args.resume) else set()
    if done:
        logger.info("续跑：已有 %d 条完成记录，将跳过", len(done))
    for i, case in enumerate(cases, 1):
        if case.case_id in done:
            logger.info("[%d/%d] %s 已完成，跳过", i, len(cases), case.case_id)
            continue
        logger.info("[%d/%d] %s (%s)", i, len(cases), case.case_id, case.task)
        rec = await run_case(
            case,
            k=args.k,
            use_rerank=not args.no_rerank,
            run_agent=not args.no_agent,
            store_enabled=getattr(args, "store_enabled", True),
        )
        if rec.env_error:
            env_blocked += 1
            logger.error(
                "环境错误（额度/鉴权）——**中止本轮**，case=%s：%s",
                case.case_id,
                (rec.hard_fails[0] if rec.hard_fails else rec.retrieval_error)[:200],
            )
            break  # 不再继续烧请求，也不把环境错误记成 case 失败
        if args.judge and not args.no_agent:
            out = await judge_mod.judge_case(case, rec.reply, rec.hard_fails)
            judge_mod.apply_judge(rec, out)
        records.append(rec)
        # ★ 逐条落盘：被中止也不丢已完成数据（见 runner.append_record 的教训注释）
        if args.out:
            append_record(rec, args.out)

    if env_blocked:
        print(
            f"\n> ⚠️ **本轮因环境错误中止**：本轮新增 {len(records)} 条，"
            f"{len(cases) - len(records) - len(done)} 条未跑。这不是 case 失败，**不得计入失败率**。\n"
        )

    all_records = _load_all_records(args.out) if args.out else [r.to_dict() for r in records]
    report = build_report(all_records)
    markdown = render_markdown(report)
    print("\n" + markdown)

    if args.out:
        report_path = Path(args.out).with_suffix(".report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("归档 → %s / %s（累计 %d 条）", args.out, report_path, len(all_records))
    else:
        logger.info("未指定 --out，本次不落盘（只打印）")
    return 0


def _load_all_records(path: str) -> list[dict]:
    """读回归档里的全部 record（含续跑前已有的）。"""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 被中断写坏的最后一行
    return out


def _calibrate(args: argparse.Namespace) -> int:
    """读校准文件（jsonl：{case_id, llm_score, human_score}）→ 一致性报告。"""
    path = Path(args.input)
    if not path.exists():
        logger.error("校准文件不存在: %s", path)
        return 2
    llm_scores: list[float] = []
    human_scores: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        if obj.get("llm_score") is None or obj.get("human_score") is None:
            continue
        llm_scores.append(float(obj["llm_score"]))
        human_scores.append(float(obj["human_score"]))

    rep = judge_mod.calibrate(llm_scores, human_scores)
    print(json.dumps(rep.__dict__, ensure_ascii=False, indent=2))
    print(f"\n阈值: {judge_mod.CALIBRATION_THRESHOLDS}")
    print("判定:", "PASS —— judge 可进批量" if rep.passed else f"FAIL —— 未达标项 {rep.failed_on}")
    # ★ D6（§20.5 #19）：**秩相关的信息量单独露出**，不参与判定、不改退出码。
    #   真实校准表是 `{5:28, 0:1, 2:1}` ⇒ PASS 可以是真的，但 `spearman` 只由 2/30 行决定。
    if rep.rank_degenerate:
        print(
            f"\n⚠ 人工分**近似同值**：众数 {rep.human_mode} 占 "
            f"{1 - (rep.informative_share or 0):.1%}，非众数仅 {rep.informative_n}/{rep.n} 行"
            f"（{(rep.informative_share or 0):.1%} < {judge_mod.INFORMATIVE_SHARE_MIN:.0%}）"
        )
        print(
            "  ⇒ `spearman` 的判别力集中在那几行上，**不要**把本表当「judge 与人工秩相关良好」引用；"
            "论文里应表述为「N 条中 M 条人机完全一致 + 其余 K 条排序正确」。"
        )
        print("  ⇒ 阈值与人工分都**不为此调整**（改人工分等于伪造标注）。")
    return 0 if rep.passed else 1


def _sanity(args: argparse.Namespace) -> int:
    """Gold Sanity Check：ERROR 存在则 exit 1（阻止进 0B）；PENDING 只提示。"""
    from evaluation.task_eval.gold_sanity import render, sanity_for_demo

    report = sanity_for_demo(args.task)
    print("\n" + render(report))
    return 0 if report.ok else 1


async def _rejudge(args: argparse.Namespace) -> int:
    """**只重判、不重跑**：用当前 judge 重算已归档 record 的分数。

    适用场景：**agent 未变、只换了 judge**。此时 reply 仍有效，
    重判只需 N 次调用（N=条数），而重跑需 ~7.5N 次 —— 省约 85%。
    """
    records = _load_all_records(args.records)
    if not records:
        logger.error("读不到 record：%s", args.records)
        return 2
    cases = {c.case_id: c for c in load_demo()}
    logger.info("重判 %d 条，judge = %s", len(records), settings.ragas_judge_model)

    out: list[dict] = []
    failed = 0
    for i, rec in enumerate(records, 1):
        case = cases.get(str(rec.get("case_id") or ""))
        if case is None:
            logger.warning("找不到 case %s，原样保留", rec.get("case_id"))
            out.append(rec)
            continue
        logger.info("[%d/%d] %s", i, len(records), case.case_id)
        result = await judge_mod.judge_case(
            case, str(rec.get("reply") or ""), rec.get("hard_fails") or []
        )
        if result is None:
            failed += 1
            logger.warning("重判失败，保留原分：%s", case.case_id)
        judge_mod.apply_judge_to_dict(rec, result, judge_model=settings.ragas_judge_model)
        out.append(rec)

    if args.out:
        p = Path(args.out)
        write_jsonl(p, out)
        logger.info("写出 %d 条 → %s（失败 %d 条保留原分）", len(out), p, failed)

    report = build_report(out)
    markdown = render_markdown(report)
    print("\n" + markdown)
    if args.out:
        rp = Path(args.out).with_suffix(".report.json")
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("报告 → %s", rp)
    return 0 if failed == 0 else 1


async def _reprobe(args: argparse.Namespace) -> int:
    """**只重跑检索探针**，更新 record 的检索侧指标（**零 LLM 成本**）。

    适用场景：检索侧**指标口径变了**（如 `kp_hit` 在元数据缺失时改记 N/A），
    而 agent/judge 的产物（reply、final_quality）仍然有效。
    重跑探针只打 TEI embedding，不调用任何 LLM ⇒ 可放心重算。
    """
    from evaluation.task_eval.retrieval_probe import probe_retrieval

    records = _load_all_records(args.records)
    if not records:
        logger.error("读不到 record：%s", args.records)
        return 2
    cases = {c.case_id: c for c in load_demo()}
    logger.info("重跑检索探针 %d 条（零 LLM 调用）", len(records))

    out: list[dict] = []
    for i, rec in enumerate(records, 1):
        case = cases.get(str(rec.get("case_id") or ""))
        if case is None:
            out.append(rec)
            continue
        logger.info("[%d/%d] %s", i, len(records), case.case_id)
        probe = await probe_retrieval(
            case.query, task_mode=case.task_mode, k=args.k, use_rerank=not args.no_rerank
        )
        _update_retrieval_fields(rec, case, probe)
        out.append(rec)

    if args.out:
        p = Path(args.out)
        write_jsonl(p, out)
        logger.info("写出 %d 条 → %s", len(out), p)
    report = build_report(out)
    print("\n" + render_markdown(report))
    if args.out:
        rp = Path(args.out).with_suffix(".report.json")
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("报告 → %s", rp)
    return 0


def _update_retrieval_fields(rec: dict, case, probe) -> None:
    """把探针结果写回 dict record 的检索侧字段（与 `runner.run_case` 同口径）。"""
    from evaluation.task_eval import metrics
    from evaluation.task_eval.runner import _all_kp

    k = 5
    rec["pack_nonempty"] = probe.ok
    rec["pack_len"] = probe.pack_len
    rec["evidence_count"] = probe.evidence_count
    rec["retrieval_ok"] = probe.ok
    rec["retrieval_status"] = probe.status
    rec["retrieval_error"] = probe.error
    top = probe.top_k(k)
    retrieved_kp = _all_kp(top)
    rec["kp_hit"] = (
        metrics.kp_coverage(case.gold.expected_kp, retrieved_kp) if retrieved_kp else None
    )
    rec["kp_mrr"] = metrics.kp_mrr(case.gold.expected_kp, [i.knowledge_points for i in top])
    rec["category_hit"] = metrics.category_hit(case.subject, [i.category for i in top])
    rec["exam_hit"] = metrics.exam_hit_at_k([i.is_exam for i in top], k)


def _backfill(args: argparse.Namespace) -> int:
    """回填**机械可算**的字段到已归档 record（**零 LLM 成本**）。

    当前支持 Generate 交付五项 —— 它们只依赖 `reply`（机械判据）与既有的
    `final_quality`（judge 已给），故**口径变更后可即时重算，不必重跑 agent/judge**。
    """
    from evaluation.task_eval import metrics

    records = _load_all_records(args.records)
    if not records:
        logger.error("读不到 record：%s", args.records)
        return 2
    cases = {c.case_id: c for c in load_demo()}
    n = 0
    for rec in records:
        if rec.get("task") != "generate":
            continue
        case = cases.get(str(rec.get("case_id") or ""))
        reply = str(rec.get("reply") or "")
        rec["gen_structure"] = metrics.structure_pass(reply)
        rec["gen_answerability"] = metrics.answerability_pass(reply)
        rec["gen_coverage"] = rec.get("kp_hit")
        fq = rec.get("final_quality")
        rec["gen_correctness"] = None if fq is None else float(fq) >= metrics.QUALITY_PASS_THRESHOLD
        rec["gen_difficulty"] = metrics.difficulty_match(
            (case.gold.expected_difficulty if case else None), None
        )
        n += 1
    logger.info("回填 Generate 交付五项：%d 条", n)

    if args.out:
        p = Path(args.out)
        write_jsonl(p, records)
        logger.info("写出 → %s", p)
    report = build_report(records)
    print("\n" + render_markdown(report))
    if args.out:
        Path(args.out).with_suffix(".report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.task_eval", description="Phase 0 任务级评测")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="跑 demo 集并出报告")
    p_run.add_argument("--task", choices=list(TASKS), default=None, help="只跑单个任务")
    p_run.add_argument("--limit", type=int, default=None, help="每个 task 各取前 N 条（0A 用 3）")
    p_run.add_argument("--k", type=int, default=5, help="检索探针 top-k（默认 5）")
    p_run.add_argument("--no-rerank", action="store_true", help="检索探针关闭重排")
    p_run.add_argument("--no-agent", action="store_true", help="只跑检索探针，不跑 agent/LLM")
    p_run.add_argument(
        "--judge", action="store_true", default=True, help="启用 LLM judge（默认开）"
    )
    p_run.add_argument("--no-judge", dest="judge", action="store_false")
    p_run.add_argument("--out", default="", help="归档 jsonl 路径（不给则只打印）")
    p_run.add_argument(
        "--demo-dir",
        default=None,
        help="case 目录（默认 evals/datasets/demo）——探针 case 用，避免污染正式集",
    )
    p_run.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="忽略已有归档、从头跑（默认会跳过已完成的 case_id 续跑）",
    )
    p_run.add_argument(
        "--store-off",
        dest="store_enabled",
        action="store_false",
        default=True,
        help="paired control：临时摘除 Store（memory 专用）——B 段不应召回，"
        "与默认（Store ON）配对可证明「召回确实来自 Store」",
    )
    p_run.set_defaults(func=lambda a: asyncio.run(_run(a)))

    p_cal = sub.add_parser("calibrate", help="LLM judge vs 人工 一致性校准")
    p_cal.add_argument("--input", required=True, help="jsonl：{case_id, llm_score, human_score}")
    p_cal.set_defaults(func=_calibrate)

    p_san = sub.add_parser("sanity", help="Gold Sanity Check（进 0B 前必跑）")
    p_san.add_argument("--task", choices=list(TASKS), default=None)
    p_san.set_defaults(func=_sanity)

    p_rj = sub.add_parser("rejudge", help="只重判不重跑（换 judge 时约省 85%% 调用）")
    p_rj.add_argument("--records", required=True, help="已有归档 jsonl")
    p_rj.add_argument("--out", default="", help="输出 jsonl（不给则只打印）")
    p_rj.set_defaults(func=lambda a: asyncio.run(_rejudge(a)))

    p_rp = sub.add_parser("reprobe", help="只重跑检索探针、更新检索侧指标（零 LLM 成本）")
    p_rp.add_argument("--records", required=True, help="已有归档 jsonl")
    p_rp.add_argument("--out", default="", help="输出 jsonl")
    p_rp.add_argument("--k", type=int, default=5)
    p_rp.add_argument("--no-rerank", action="store_true")
    p_rp.set_defaults(func=lambda a: asyncio.run(_reprobe(a)))

    p_bf = sub.add_parser("backfill", help="回填机械可算字段（如 Generate 交付五项，零 LLM 成本）")
    p_bf.add_argument("--records", required=True)
    p_bf.add_argument("--out", default="")
    p_bf.set_defaults(func=_backfill)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
