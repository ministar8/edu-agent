"""Pack→Agent 输入契约门禁：验证工具载荷在**进入 Agent 之前**的形态。

Agent 实际看到的是 ToolMessage.content = json.dumps(payload, ensure_ascii=False)
（见 langgraph.prebuilt.tool_node.msg_content_output）。本门禁盯两层：

1. **结构契约**：必备键、status 三态、empty/error 说明句、docs 引用字段
2. **披露契约**：answer-hidden 模式下，序列化后的 ToolMessage **不得**含
   答案字段 / 答案正文 / 题号（practice/learn/method）

与 leakage_gate 的分工：
- leakage_gate  → Evidence Pack 裁剪是否正确（pack 内部）
- 本门禁        → 裁剪结果转成 Agent 输入后是否仍守约（含 empty 文案、降级注记、序列化面）

用法：
    uv run python scripts/agent_input_contract_gate.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langgraph.prebuilt.tool_node import msg_content_output  # noqa: E402

from rag.evidence import FusedEvidence, TextEvidence  # noqa: E402
from rag.evidence_policy import apply_evidence_policy, finalize_with_layer_ranking  # noqa: E402
from rag.task_policy import policy_for_mode, resolve_task_policy  # noqa: E402
from schema.evidence import RetrievalResult  # noqa: E402

# —— 泄漏面（与 leakage_gate 对齐）——
_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer|correct_answer|qa\.answer", re.I)
_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】|正确答案|标准答案")

# answer-hidden 的模式：ToolMessage 里不得出现答案/题号
_HIDDEN_MODES = ("learn", "method", "practice")
# 允许题号的模式
_QID_OK_MODES = ("grade", "explain", "verify")

_REQUIRED_KEYS = ("status", "query", "context", "docs", "sources")


def _tool_message(payload: dict[str, Any]) -> str:
    """还原 Agent 实际看到的 ToolMessage.content。"""
    return msg_content_output(payload)


def _fixture_fused() -> FusedEvidence:
    """含答案/题号/legacy 的候选包，模拟最坏泄漏面。"""
    return FusedEvidence(
        text_evidences=[
            TextEvidence(
                evidence_id="i1",
                content="## 2019-Q11\n**题干**：BST 删除…\n- A. …\n- B. …",
                source="items.md",
                chunk_id="exam-2019-Q11-items-001",
                metadata={
                    "doc_role": "exam_item",
                    "question_id": "2019-Q11",
                    "answer_key": "B",
                    "reference_answer": "因为…",
                    "kb_depth": "exams",
                },
            ),
            TextEvidence(
                evidence_id="a1",
                content="答案：B\n解析：故选 B。",
                source="answer.md",
                chunk_id="exam-2019-Q11-answer-001",
                metadata={
                    "doc_role": "exam_answer",
                    "explanation_status": "scan",
                    "answer_key": "B",
                    "kb_depth": "exams",
                },
            ),
            TextEvidence(
                evidence_id="b1",
                content="BST 删除分三种情况。",
                source="basic.md",
                chunk_id="basic-ds-tree-bst-001",
                metadata={"doc_role": "textbook", "kb_depth": "basic", "score": 0.9},
            ),
            TextEvidence(
                evidence_id="m1",
                content="方法：先看孩子数。",
                source="method.md",
                chunk_id="advanced-ds-tree-bst_ops-001",
                metadata={"doc_role": "method", "kb_depth": "advanced", "score": 0.8},
            ),
        ],
        final_context="…\n答案：B\n…",
    )


def _payload_from_fused(mode: str, fused: FusedEvidence, query: str) -> dict[str, Any]:
    """fused → finalize → release → 对外载荷（与 tools._retrieve_payload 同构）。"""
    policy = policy_for_mode(mode)  # type: ignore[arg-type]
    packed = finalize_with_layer_ranking(fused, policy, keep=5)
    out, _flags = apply_evidence_policy(packed, policy)
    docs = []
    for e in out.text_evidences:
        docs.append(
            {
                "evidence_id": e.evidence_id,
                "source": e.source,
                "section_path": e.section_path,
                "chunk_id": e.chunk_id,
                "score": e.score,
                "rerank_score": e.rerank_score,
                "knowledge_points": list(e.knowledge_points),
                "excerpt": (e.content or "")[:400],
            }
        )
    ctx = out.final_context or "知识库中未找到相关内容。"
    if not out.final_context.strip():
        return RetrievalResult(
            status="empty", query=query, context=ctx, sources=[], docs=docs
        ).as_tool_payload()
    return RetrievalResult(
        status="ok",
        query=query,
        context=ctx,
        sources=[str(s) for s in (out.sources or [])],
        docs=docs,
    ).as_tool_payload()


# ── 契约检查 ──────────────────────────────────────────────


def check_structure(payload: dict[str, Any], label: str) -> list[str]:
    fails: list[str] = []
    for k in _REQUIRED_KEYS:
        if k not in payload:
            fails.append(f"{label}: 缺必备键 {k}")
    status = payload.get("status")
    if status not in ("ok", "empty", "error"):
        fails.append(f"{label}: status 非法 {status!r}")
    if not isinstance(payload.get("docs"), list):
        fails.append(f"{label}: docs 不是 list")
    try:
        msg = _tool_message(payload)
    except Exception as e:  # noqa: BLE001
        fails.append(f"{label}: ToolMessage 无法序列化: {e}")
        return fails
    if not isinstance(msg, str) or not msg:
        fails.append(f"{label}: ToolMessage 为空")
    return fails


def check_empty_and_error(payload: dict[str, Any], label: str) -> list[str]:
    fails: list[str] = []
    status = payload.get("status")
    ctx = str(payload.get("context") or "")
    if status == "empty":
        if not re.search(r"未找到|未检索到|无相关|没有找到", ctx):
            fails.append(f"{label}: empty 未如实说明「未检索到」: {ctx[:60]!r}")
    if status == "error":
        kind = payload.get("error_kind")
        if kind not in ("unavailable", "internal"):
            fails.append(f"{label}: error 缺 error_kind: {kind!r}")
        if not re.search(r"失败|不可用|稍后|错误", ctx):
            fails.append(f"{label}: error 未说明失败: {ctx[:60]!r}")
    return fails


def check_disclosure(payload: dict[str, Any], mode: str, label: str) -> list[str]:
    """answer-hidden 模式：Agent 输入面不得含答案/题号。"""
    fails: list[str] = []
    if mode not in _HIDDEN_MODES:
        return fails
    msg = _tool_message(payload)
    meta_blob = str(payload.get("docs") or []) + str(payload)
    if _ANS_FIELD_RE.search(meta_blob):
        fails.append(f"{label}: payload 含答案字段")
    if _ANS_FIELD_RE.search(msg):
        fails.append(f"{label}: 序列化面含答案字段")
    if _ANS_BODY_RE.search(str(payload.get("context") or "")) or _ANS_BODY_RE.search(msg):
        fails.append(f"{label}: 含答案正文")
    if mode not in _QID_OK_MODES and _QID_RE.search(msg):
        fails.append(f"{label}: 含真题题号")
    return fails


def check_layer_notes(payload: dict[str, Any], label: str) -> list[str]:
    """降级 / fallback 补入注记格式不得自相矛盾。"""
    fails: list[str] = []
    ctx = str(payload.get("context") or "")
    if "降级" in ctx and not re.search(r"保留 \d+/\d+", ctx):
        fails.append(f"{label}: 降级注记缺保留数")
    if "fallback" in ctx and "legacy" not in ctx:
        fails.append(f"{label}: fallback 注记缺来源说明")
    return fails


def check_tool_contract_note() -> list[str]:
    """检索类工具的 description 必须带载荷契约说明（模型侧约定）。"""
    fails: list[str] = []
    from agents.tools import (
        aknowledge_search,
        asearch_question_templates,
        asearch_standard_answer,
        atext_search,
    )

    tools = (
        aknowledge_search,
        atext_search,
        asearch_standard_answer,
        asearch_question_templates,
    )
    for t in tools:
        desc = t.description or ""
        name = getattr(t, "name", "?")
        if "status" not in desc or "context" not in desc:
            fails.append(f"tool {name}: description 缺载荷契约说明")
    return fails


def _tei_available() -> bool:
    """快速探活 embedding 端点（2s 超时）；不可用则 live 段跳过。

    GET /embeddings 会 405（OpenAI 兼容路由只收 POST）——
    4xx = 服务在听；5xx / 连接失败 = 不可用。
    """
    import urllib.error
    import urllib.request

    from core.settings import settings

    base = str(getattr(settings, "EMBEDDING_API_BASE", "") or "").rstrip("/")
    if not base:
        return False
    url = base if base.endswith("/embeddings") else f"{base}/embeddings"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:  # noqa: BLE001
        return False


# ── 运行 ──────────────────────────────────────────────


def run_fixture() -> list[str]:
    print("==== fixture: 结构 / 披露 / empty·error ====")
    fails: list[str] = []
    fused = _fixture_fused()

    for mode in ("learn", "method", "practice", "grade", "explain", "verify"):
        p = _payload_from_fused(mode, fused, "BST 删除怎么做？")
        label = f"fixture/{mode}"
        fails += check_structure(p, label)
        fails += check_empty_and_error(p, label)
        fails += check_disclosure(p, mode, label)
        fails += check_layer_notes(p, label)
        msg = _tool_message(p)
        print(
            f"  [{mode}] status={p.get('status')} docs={len(p.get('docs') or [])} "
            f"msg_len={len(msg)}"
        )

    empty = RetrievalResult(
        status="empty", query="火星文检索", context="知识库中未找到相关内容。"
    ).as_tool_payload()
    fails += check_structure(empty, "fixture/empty")
    fails += check_empty_and_error(empty, "fixture/empty")
    print(f"  [empty] context={empty.get('context')!r}")

    err = RetrievalResult(
        status="error",
        query="x",
        context="检索失败：知识库服务暂时不可用，请稍后重试",
        error="timeout",
        error_kind="unavailable",
    ).as_tool_payload()
    fails += check_structure(err, "fixture/error")
    fails += check_empty_and_error(err, "fixture/error")
    print(f"  [error] kind={err.get('error_kind')} context={err.get('context')[:40]!r}")
    return fails


async def run_live() -> list[str]:
    print("==== live: 真检索 → ToolMessage ====")
    fails: list[str] = []

    if not _tei_available():
        print("  SKIP: TEI embedding 不可用（fixture 段已覆盖结构/披露契约）")
        return fails

    from agents.tools import _retrieve_payload  # noqa: PLC2701

    cases = [
        ("learn", "什么是二叉排序树？"),
        ("method", "BST 删除怎么做？"),
        ("practice", "给我一道 BST 删除练习"),
        ("grade", "2019-Q2 我选 B，请批改"),
        ("explain", "2019-Q2 为什么树的后根遍历对应二叉树中序？"),
        ("verify", "BST 删除考过哪些真题？"),
        ("learn", "火星文完全不存在的检索词 zzzqqq"),
    ]
    for mode, q in cases:
        payload = await _retrieve_payload(q, k=5, agent_prior=mode)
        label = f"live/{mode}/{q[:12]}"
        fails += check_structure(payload, label)
        fails += check_empty_and_error(payload, label)

        actual_mode = resolve_task_policy(q, agent_prior=mode).task_mode
        fails += check_disclosure(payload, actual_mode, label)
        fails += check_layer_notes(payload, label)
        print(
            f"  [{actual_mode}] status={payload.get('status')} "
            f"docs={len(payload.get('docs') or [])} "
            f"msg_len={len(_tool_message(payload))} q={q[:16]!r}"
        )
    return fails


async def main() -> int:
    fails = run_fixture()

    print("==== tool description 契约 ====")
    note_fails = check_tool_contract_note()
    fails += note_fails
    print("  " + ("OK" if not note_fails else "FAIL"))

    fails += await run_live()

    if fails:
        print(f"\nAGENT INPUT CONTRACT FAIL {len(fails)}")
        for f in fails:
            print(" -", f)
        return 1
    print("\nAGENT INPUT CONTRACT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
