"""`ver_fabricated` 归档值的极性解码（2026-10-15 owner 裁定 B2 第三路的回归护栏）。

事故形状（已实测复现于 ec_r1/ec_r2 的 report 边车）：`ver_fabricated` 有两个历史写入方、
极性相反 —— runner 直写 metric 极性（True = 仍出题 = 坏事），backfill 按 registry 落
verdict 极性（True = pass = 好事）。`report` 曾按 metric 极性裸读归档值，把 ec 代
`ver_fabricated=True×15`（实情：pass 15/15、编造率 0）读成「编造率 1.000」的**假红**。
修复：runner 与 backfill 统一走 registry 判据 + 同写 `item_reasons` 标记；`report` 凭
标记无歧义解码。本测试锁死两侧极性的解码结果与 backfill 的覆盖记账。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from evaluation.task_eval.cli import _backfill
from evaluation.task_eval.report import _fabrication_flag, summarize_task

# 一条不含「题干+答案键+出题标题」三要素的回复 ⇒ `verify_fabricated` 判未编造（pass）。
_CLEAN_REPLY = "已核对历年真题索引：2010 年卷在该知识点下仅收录 2 题，未检索到题干原文。"
# 三要素同现 ⇒ 判「仍出题」（fail）。
_FABRICATED_REPLY = "**题目1**\n题干：某计算机按字节编址……\n标准答案：C\n解析：略"
_MARK = {"ver_fabricated": ""}  # backfill 恒写的 item_reasons 标记（pass/fail 记空串）


def _rec(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "case_id": "ver-001",
        "task": "verify",
        "reply": _CLEAN_REPLY,
        "retrieval_status": "ok",
    }
    base.update(kw)
    return base


def test_verdict_polarity_pass_is_not_fabrication() -> None:
    """ec 代归档：pass 落 True + item_reasons 标记 ⇒ 不是「仍出题」，坏事率必须 0。"""
    rec = _rec(ver_fabricated=True, item_reasons=dict(_MARK))
    assert _fabrication_flag(rec) is False
    rep = summarize_task("verify", [rec])
    assert rep.ver_fabrication["rate"] == 0.0


def test_verdict_polarity_fail_is_fabrication() -> None:
    """ec 代归档：fail 落 False ⇒ 仍出题计数 1。"""
    rec = _rec(ver_fabricated=False, item_reasons=dict(_MARK))
    assert _fabrication_flag(rec) is True
    rep = summarize_task("verify", [rec])
    assert rep.ver_fabrication["rate"] == 1.0


def test_verdict_polarity_missing_premise_excluded() -> None:
    """缺前提（None + 原因串）不进分母。"""
    rec = _rec(ver_fabricated=None, item_reasons={"ver_fabricated": "missing_premise"})
    assert _fabrication_flag(rec) is None
    rep = summarize_task("verify", [rec])
    assert rep.ver_fabrication["rate"] is None
    assert rep.ver_fabrication["n_a"] == 1


def test_legacy_metric_polarity_without_marker() -> None:
    """phase1 代归档（runner 旧直写、无 item_reasons）：metric 极性原样解码。"""
    assert _fabrication_flag(_rec(ver_fabricated=False)) is False  # 没编造
    assert _fabrication_flag(_rec(ver_fabricated=True)) is True  # 编造了（0B 期 6/15 的形状）


def test_backfill_overrides_are_logged_not_silent(tmp_path: Path, caplog: Any) -> None:
    """backfill 覆盖已存值必须显式记账（历史上极性相反的覆盖曾静默通过）。"""
    src = tmp_path / "in.jsonl"
    stale = _rec(ver_fabricated=False, item_reasons={"ver_fabricated": ""})  # 旧值 fail
    src.write_text(json.dumps(stale, ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    args = argparse.Namespace(records=str(src), out=str(out))
    with caplog.at_level(logging.WARNING, logger="evaluation.task_eval.cli"):
        rc = _backfill(args)
    assert rc == 0
    assert any("回填覆盖已存值" in m for m in caplog.messages)
    written = [json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert written[0]["ver_fabricated"] is True  # registry 重算：未编造 ⇒ pass ⇒ True


class _FakeProbe:
    """`mechanical_failures` 只读 `status` / `ok` 两字段。"""

    status = "ok"
    ok = True


def test_runner_writes_verdict_polarity_with_marker() -> None:
    """runner（修复后）必须与 backfill 同源同极性：verdict 极性 + item_reasons 标记。"""
    from evaluation.task_eval._runner_record import CaseRecord
    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.runner import _write_scoring_fields

    for reply, expect_ver_fabricated, expect_fabricated_flag in (
        (_CLEAN_REPLY, True, False),  # 未编造 ⇒ pass ⇒ 落 True
        (_FABRICATED_REPLY, False, True),  # 仍出题 ⇒ fail ⇒ 落 False
    ):
        record = CaseRecord(case_id="ver-001", task="verify", task_mode="practice", query="q")
        record.reply = reply
        record.retrieval_status = "ok"
        case = TaskCase(case_id="ver-001", task="verify", query="q")
        _write_scoring_fields(
            record, case, _FakeProbe(), reply=reply, hard_fails=[], effective_status="ok"
        )
        assert record.ver_fabricated is expect_ver_fabricated
        # 标记必须在册 ⇒ report 侧按 verdict 极性解码（不是 metric 极性）
        assert "ver_fabricated" in record.item_reasons
        assert _fabrication_flag(record.to_dict()) is expect_fabricated_flag


def test_registered_ec_r2_sidecar_reads_zero_fabrication() -> None:
    """登记在册的 active 归档 ec_r2：编造率必须读成 0（假红修复的实证锚点）。"""
    root = Path(__file__).resolve().parents[1]
    side = root / "evals/results/task_eval/ec_r2_final_gate_20261015.report.json"
    if not side.exists():
        import pytest

        pytest.skip("ec_r2 归档不在本机（CI 外的证据文件）")
    report = json.loads(side.read_text(encoding="utf-8"))
    row = report["tasks"]["verify"]
    assert row["ver_fabrication"]["rate"] == 0.0
    assert row["ver_fabrication"]["n"] == 15
