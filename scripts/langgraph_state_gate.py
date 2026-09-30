"""LangGraph State 闭环硬门禁。

把代码里已有约定钉成可回归断言（改 teaching_graph / service / checkpointer / memory 注入时必跑）：

1. **checkpoint restart** — 同一 checkpointer 数据源 + 同一 thread_id：
   app A 写入 → 关闭连接 → **app B 重新打开同一 SQLite** 仍能读到同一批消息。
   （防止测成「内存对象没销毁」）
2. **trim state integrity** — trim 只裁「本轮模型输入」，
   **checkpoint 里的 State messages 内容/数量不得被改**。
   辅助：checkpoint_messages_after >= model_input_messages。
3. **interrupt / resume** — interrupt → checkpoint 记录中断态 →
   Command(resume=...) 从**中断点继续**（不重跑 START），最终到 END。
4. **store rehydration** — Thread A 写入 Store（跨 thread 长期记忆）→
   Thread B 新一轮 `load_memory` 把工作记忆卡注入 state
   （验的是 Store，不是 checkpoint 里残留的 memory）。

用法：
    uv run python scripts/langgraph_state_gate.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typing import Annotated  # noqa: E402

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from langchain_core.runnables import RunnableConfig  # noqa: E402
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.graph.message import add_messages  # noqa: E402
from langgraph.types import Command, interrupt  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "results" / "system_validation" / "langgraph_state"

results: list[tuple[str, bool, str]] = []
evidence: dict[str, Any] = {}


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def _msg_ids(msgs: list[Any]) -> list[str]:
    return [str(getattr(m, "id", "") or i) for i, m in enumerate(msgs)]


def _msg_sig(msgs: list[Any]) -> list[tuple[str, str, str]]:
    """(id, type, content 前 40 字) —— 用于 trim 前后逐条比对。"""
    out = []
    for m in msgs:
        out.append(
            (
                str(getattr(m, "id", "") or ""),
                type(m).__name__,
                str(getattr(m, "content", "") or "")[:40],
            )
        )
    return out


async def _fake_supervisor_factory(captured: list[int] | None = None):
    """构造假 inner_supervisor：记录模型输入条数，返回固定回复（状态测试不跑真 LLM）。"""

    class _FakeSup:
        async def ainvoke(self, input: dict, config: Any = None, **kw: Any) -> dict:
            msgs = list(input.get("messages") or [])
            if captured is not None:
                captured.append(len(msgs))
            return {
                "messages": [
                    AIMessage(content=f"reply-{len(msgs)}", id=f"ai-{uuid.uuid4().hex[:8]}")
                ]
            }

    return _FakeSup()


# ── ① checkpoint restart ────────────────────────────────


async def test_checkpoint_restart(tmp: Path) -> bool:
    db = tmp / "checkpoints_restart.db"
    thread = f"gate-restart-{uuid.uuid4().hex[:8]}"
    config = RunnableConfig(configurable={"thread_id": thread, "user_id": "gate-user"})

    import agents.teaching_graph as tg
    from memory.window import trim_conversation  # noqa: F401  （确保依赖可导入）

    original = tg.inner_supervisor
    tg.inner_supervisor = await _fake_supervisor_factory()
    try:
        # app A：写入
        async with AsyncSqliteSaver.from_conn_string(str(db)) as saver_a:
            await saver_a.setup()
            graph_a = tg.build_teaching_graph()
            graph_a.checkpointer = saver_a
            await graph_a.ainvoke({"messages": [HumanMessage(content="A轮问题")]}, config=config)
            await graph_a.ainvoke({"messages": [HumanMessage(content="A轮问题二")]}, config=config)
            snap_a = await graph_a.aget_state(config=config)
            ids_a = _msg_ids(list(snap_a.values.get("messages") or []))
            n_a = len(ids_a)
        # 显式断开 A，确保 B 不是复用内存对象
        del graph_a

        # app B：同一 SQLite 文件、同一 thread_id 的全新图 + 全新 saver
        async with AsyncSqliteSaver.from_conn_string(str(db)) as saver_b:
            await saver_b.setup()
            graph_b = tg.build_teaching_graph()
            graph_b.checkpointer = saver_b
            snap_b = await graph_b.aget_state(config=config)
            ids_b = _msg_ids(list(snap_b.values.get("messages") or []))
            # 不同 thread 必须是空的（证明不是全局内存残留）
            other = RunnableConfig(
                configurable={
                    "thread_id": f"gate-empty-{uuid.uuid4().hex[:6]}",
                    "user_id": "gate-user",
                }
            )
            snap_other = await graph_b.aget_state(config=other)
            n_other = len(snap_other.values.get("messages") or [])
    finally:
        tg.inner_supervisor = original

    ok = n_a >= 2 and ids_a == ids_b and n_other == 0
    detail = f"n_a={n_a} ids_match={ids_a == ids_b} other_thread_msgs={n_other} db={db.name}"
    evidence["checkpoint_restart"] = {
        "db": db.name,
        "thread_id": thread,
        "n_app_a": n_a,
        "ids_app_a": ids_a,
        "ids_app_b": ids_b,
        "other_thread_msgs": n_other,
    }
    record("checkpoint restart", ok, detail)
    return ok


# ── ② trim state integrity ──────────────────────────────


async def test_trim_state_integrity(tmp: Path) -> bool:
    from core import settings

    max_msgs = int(settings.MEMORY_HISTORY_MAX_MESSAGES)
    db = tmp / "checkpoints_trim.db"
    thread = f"gate-trim-{uuid.uuid4().hex[:8]}"
    config = RunnableConfig(configurable={"thread_id": thread, "user_id": "gate-user"})

    import agents.teaching_graph as tg

    captured: list[int] = []
    original = tg.inner_supervisor
    tg.inner_supervisor = await _fake_supervisor_factory(captured)
    try:
        async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
            await saver.setup()
            graph = tg.build_teaching_graph()
            graph.checkpointer = saver

            # 造出超过 max_messages 的历史（每轮 Human+AI = 2 条）
            turns = (max_msgs // 2) + 5
            for i in range(turns):
                await graph.ainvoke({"messages": [HumanMessage(content=f"问题{i}")]}, config=config)

            before = await graph.aget_state(config=config)
            before_msgs = list(before.values.get("messages") or [])
            before_sig = _msg_sig(before_msgs)

            # 再来一轮：此时 trim 必然发生（chat 条数 > max_msgs）
            await graph.ainvoke({"messages": [HumanMessage(content="裁剪后的一轮")]}, config=config)

            after = await graph.aget_state(config=config)
            after_msgs = list(after.values.get("messages") or [])
            after_sig = _msg_sig(after_msgs)
    finally:
        tg.inner_supervisor = original

    model_input_lens = captured or [0]
    last_input = model_input_lens[-1]
    # ★ 硬断言：trim 后 checkpoint 的 State 内容不得被改（只允许追加新消息）
    prefix_unchanged = after_sig[: len(before_sig)] == before_sig
    not_shrunk = len(after_msgs) >= len(before_msgs)
    # 辅助：模型输入确实被裁过
    trimmed_applied = last_input <= max_msgs + 2  # +System 记忆卡余量
    aux_ok = len(after_msgs) >= last_input

    ok = prefix_unchanged and not_shrunk and trimmed_applied and aux_ok
    detail = (
        f"before={len(before_msgs)} after={len(after_msgs)} "
        f"model_input_last={last_input} max={max_msgs} "
        f"prefix_unchanged={prefix_unchanged} trimmed={trimmed_applied}"
    )
    evidence["trim_state_integrity"] = {
        "before_ids": _msg_ids(before_msgs),
        "after_ids": _msg_ids(after_msgs),
        "model_input_lens": model_input_lens,
        "max_messages": max_msgs,
        "prefix_unchanged": prefix_unchanged,
        "not_shrunk": not_shrunk,
        "aux_checkpoint_ge_input": aux_ok,
    }
    record("trim state integrity", ok, detail)
    return ok


# ── ③ interrupt / resume ────────────────────────────────


class _IState(TypedDict):
    messages: Annotated[list, add_messages]


async def test_interrupt_resume(tmp: Path) -> bool:
    db = tmp / "checkpoints_interrupt.db"
    thread = f"gate-interrupt-{uuid.uuid4().hex[:8]}"
    config = RunnableConfig(configurable={"thread_id": thread, "user_id": "gate-user"})

    exec_log: list[str] = []

    def node_start(state: _IState) -> dict:
        exec_log.append("start")
        return {"messages": [AIMessage("from-start", id="m-start")]}

    def node_ask(state: _IState) -> dict:
        exec_log.append("ask")
        answer = interrupt({"question": "请确认"})
        return {"messages": [AIMessage(f"resumed:{answer}", id="m-ask")]}

    def node_end(state: _IState) -> dict:
        exec_log.append("end")
        return {"messages": [AIMessage("done", id="m-end")]}

    builder: StateGraph = StateGraph(_IState)
    builder.add_node("start", node_start)
    builder.add_node("ask", node_ask)
    builder.add_node("end", node_end)
    builder.add_edge(START, "start")
    builder.add_edge("start", "ask")
    builder.add_edge("ask", "end")
    builder.add_edge("end", END)

    async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
        await saver.setup()
        graph = builder.compile(checkpointer=saver)

        first = await graph.ainvoke({"messages": [HumanMessage(content="请开始")]}, config=config)
        has_interrupt = "__interrupt__" in first or bool(
            getattr(first, "get", lambda *_: None)("__interrupt__")
        )
        snap = await graph.aget_state(config=config)
        next_nodes = list(snap.next or [])
        tasks_interrupted = any(getattr(t, "interrupts", None) for t in (snap.tasks or []))
        log_after_first = list(exec_log)

        await graph.ainvoke(Command(resume="CONFIRMED"), config=config)
        snap2 = await graph.aget_state(config=config)
        log_after_resume = list(exec_log)
        texts = " ".join(
            str(getattr(m, "content", "")) for m in (snap2.values.get("messages") or [])
        )

    # 硬断言
    stopped_at_ask = "ask" in log_after_first and "end" not in log_after_first
    # resume 后 start 不得重跑（否则是「从 START 重来一遍」）
    start_once = log_after_resume.count("start") == 1
    continued_to_end = "end" in log_after_resume
    resume_value_used = "resumed:CONFIRMED" in texts

    # service 侧 Command(resume=...) 接线（静态约定）
    svc = (ROOT / "src" / "service" / "service.py").read_text(encoding="utf-8")
    service_wired = "Command(resume=" in svc.replace(" ", "")

    ok = stopped_at_ask and start_once and continued_to_end and service_wired
    detail = (
        f"log1={log_after_first} log2={log_after_resume} "
        f"next={next_nodes} tasks_interrupted={tasks_interrupted} "
        f"resume_value={resume_value_used} service_wired={service_wired}"
    )
    evidence["interrupt_resume"] = {
        "log_after_first": log_after_first,
        "log_after_resume": log_after_resume,
        "next_after_interrupt": next_nodes,
        "tasks_interrupted": tasks_interrupted,
        "resume_value_used": resume_value_used,
        "service_command_resume_wired": service_wired,
        "has_interrupt_key": bool(has_interrupt),
    }
    record("interrupt / resume", ok, detail)
    return ok


# ── ④ store rehydration ─────────────────────────────────


async def test_store_rehydration(tmp: Path) -> bool:
    """Thread A 写 Store → Thread B 新一轮 load_memory 注入工作记忆卡。"""
    from core import settings
    from memory import get_sqlite_store
    from memory.remember import record_grade
    from memory.runtime import set_store
    from memory.working import abuild_memory_card

    uid = f"gate-store-{uuid.uuid4().hex[:8]}"
    topic = "AVL旋转调整"
    store_db = tmp / "store_rehydration.db"

    # 隔离 store 文件，避免污染真实 store.db
    old_store_path = settings.SQLITE_STORE_PATH
    old_vec = settings.MEMORY_STORE_VECTOR_ENABLED
    settings.SQLITE_STORE_PATH = str(store_db)
    settings.MEMORY_STORE_VECTOR_ENABLED = False

    import agents.teaching_graph as tg

    original = tg.inner_supervisor
    tg.inner_supervisor = await _fake_supervisor_factory()
    try:
        async with get_sqlite_store() as store:
            set_store(store)
            # Thread A：写两条低分 grade → 触发 weak_topics
            for i in range(2):
                await record_grade(
                    user_id=uid,
                    topic=topic,
                    score=20.0,
                    error_analysis=f"错误分析{i}",
                    stem=f"题干{i}：AVL 插入后如何旋转",
                    thread_id="thread-A",
                )
            card_direct = await abuild_memory_card(store, uid)

            # Thread B：新 thread，同一 user_id，走 teaching_graph 全链
            thread_b = f"thread-B-{uuid.uuid4().hex[:6]}"
            config_b = RunnableConfig(configurable={"thread_id": thread_b, "user_id": uid})
            db = tmp / "checkpoints_store.db"
            async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
                await saver.setup()
                graph = tg.build_teaching_graph()
                graph.checkpointer = saver
                await graph.ainvoke(
                    {"messages": [HumanMessage(content="我最近学得怎么样？")]}, config=config_b
                )
                snap = await graph.aget_state(config=config_b)
                msgs = list(snap.values.get("messages") or [])
        set_store(None)
    finally:
        tg.inner_supervisor = original
        settings.SQLITE_STORE_PATH = old_store_path
        settings.MEMORY_STORE_VECTOR_ENABLED = old_vec

    # 记忆卡应来自 Store，且注入 Thread B 的 state（固定 ID 的 SystemMessage）
    from agents.teaching_graph import MEMORY_CARD_MESSAGE_ID

    card_msgs = [
        m
        for m in msgs
        if isinstance(m, SystemMessage)
        and str(getattr(m, "id", "") or "") == MEMORY_CARD_MESSAGE_ID
    ]
    card_text = str(card_msgs[0].content) if card_msgs else ""
    # 硬断言：不是「state 里残留」，而是 Thread B 首轮就从 Store 重建
    card_has_topic = topic[:2] in card_text or topic in card_text or "薄弱" in card_text
    card_matches_store = bool(card_direct) and (
        card_direct[:20] in card_text or card_text[:20] in card_direct
    )
    ok = (
        bool(card_msgs)
        and card_has_topic
        and card_matches_store
        and thread_b.startswith("thread-B")
    )

    detail = (
        f"card_in_B={bool(card_msgs)} card_len={len(card_text)} "
        f"has_topic={card_has_topic} store_card_len={len(card_direct or '')}"
    )
    evidence["store_rehydration"] = {
        "user_id": uid,
        "topic": topic,
        "thread_a": "thread-A",
        "thread_b": thread_b,
        "card_from_store": card_direct,
        "card_in_thread_b_state": card_text,
        "card_message_id": str(getattr(card_msgs[0], "id", "")) if card_msgs else "",
    }
    record("store rehydration", ok, detail)
    return ok


# ── main ────────────────────────────────────────────────


async def main() -> int:
    print("==== LangGraph State Gate ====", flush=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="langgraph_state_gate_"))
    try:
        await test_checkpoint_restart(tmp)
        await test_trim_state_integrity(tmp)
        await test_interrupt_resume(tmp)
        await test_store_rehydration(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} PASS")
    evidence["_summary"] = {
        "passed": passed,
        "total": total,
        "cases": {n: ok for n, ok, _ in results},
    }
    out = EVIDENCE_DIR / "state_gate.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence → {out}")

    if passed != total:
        print("exit_code=1")
        return 1
    print("exit_code=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
