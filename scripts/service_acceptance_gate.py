"""Service 层验收门禁：HTTP 面（鉴权 / invoke / SSE / 会话 / 出题批改）。

分层：
- L1 `agent_input_contract_gate`  → 进 Agent 的 Evidence Pack 契约
- L2 `agent_behavior_smoke`      → Agent 输出行为（真 LLM 软断言）
- 本脚本                         → **用户可见 HTTP 面**与上两层行为一致

用 httpx.ASGITransport 进程内打 FastAPI app，不占端口、不依赖 uvicorn。

用法：
    uv run python scripts/service_acceptance_gate.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402

_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
_EMPTY_ACK_RE = re.compile(r"未检索到|未找到|没有找到|无法提供|无相关")

fails: list[str] = []
notes: list[str] = []


def ok(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {label}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL {label}" + (f"  ({detail})" if detail else ""))
        fails.append(f"{label}: {detail}")


def note(text: str) -> None:
    notes.append(text)
    print(f"  note: {text}")


def parse_sse(raw: str) -> list[dict[str, Any]]:
    """解析 `data: {...}` / `data: [DONE]` 事件流。"""
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            events.append({"type": "_done"})
            continue
        try:
            events.append(json.loads(payload))
        except Exception:  # noqa: BLE001
            events.append({"type": "_unparsed", "content": payload[:80]})
    return events


async def _llm_available() -> bool:
    """探活默认模型；不可用则 LLM 相关用例跳过（HTTP 契约段仍跑）。"""
    try:
        from langchain_core.messages import HumanMessage

        from core import get_model, settings

        m = get_model(settings.DEFAULT_MODEL, temperature=0.0)
        r = await m.ainvoke([HumanMessage(content="ping")])
        return getattr(r, "content", None) is not None
    except Exception as e:  # noqa: BLE001
        notes.append(f"LLM 不可用，跳过 invoke/stream/questions 用例: {type(e).__name__}: {e}")
        return False


async def run() -> int:
    from service.service import app

    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as client,
        app.router.lifespan_context(app),
    ):
        suffix = uuid.uuid4().hex[:8]
        user_a = {"username": f"svc_a_{suffix}", "password": "svc-pass-123"}
        user_b = {"username": f"svc_b_{suffix}", "password": "svc-pass-123"}
        llm_ok = await _llm_available()
        print(f"LLM 可用 = {llm_ok}")

        # ── 1. 健康与鉴权 ──
        print("==== 健康 / 鉴权 ====")
        r = await client.get("/health")
        ok("GET /health", r.status_code == 200, f"status={r.status_code}")

        r = await client.post("/api/invoke", json={"message": "hi"})
        ok("匿名 invoke 被拒", r.status_code == 401, f"status={r.status_code}")

        r = await client.post("/api/auth/register", json=user_a)
        ok(
            "register A",
            r.status_code == 200 and r.json().get("access_token"),
            f"status={r.status_code}",
        )
        token_a = r.json().get("access_token") if r.status_code == 200 else ""
        hdr_a = {"Authorization": f"Bearer {token_a}"}

        r = await client.post("/api/auth/register", json=user_b)
        token_b = r.json().get("access_token") if r.status_code == 200 else ""
        hdr_b = {"Authorization": f"Bearer {token_b}"}
        ok("register B", r.status_code == 200 and bool(token_b), f"status={r.status_code}")

        r = await client.get("/api/auth/me", headers=hdr_a)
        ok(
            "GET /auth/me",
            r.status_code == 200 and r.json().get("username") == user_a["username"],
        )

        r = await client.get("/api/info", headers=hdr_a)
        ok(
            "GET /api/info",
            r.status_code == 200 and "agents" in r.json(),
            f"status={r.status_code}",
        )

        # ── 2. invoke 契约 + 多轮（依赖 LLM）──
        print("==== invoke / history / threads ====")
        thread_id = f"svc-thread-{suffix}"
        if not llm_ok:
            note("跳过 invoke 契约（LLM 不可用）")
        else:
            r = await client.post(
                "/api/invoke",
                headers=hdr_a,
                json={"message": "什么是二叉排序树？", "thread_id": thread_id},
            )
            ok("invoke ok", r.status_code == 200, f"status={r.status_code}")
            body = r.json() if r.status_code == 200 else {}
            ok("invoke type=ai", body.get("type") == "ai", f"type={body.get('type')}")
            ok(
                "invoke content 非空",
                bool(str(body.get("content") or "").strip()),
                f"len={len(str(body.get('content') or ''))}",
            )
            ok("invoke 有 run_id", bool(body.get("run_id")), f"run_id={body.get('run_id')!r}")

            r = await client.post(
                "/api/invoke",
                headers=hdr_a,
                json={
                    "message": "2026 年 408 真题第 1 题官方答案是什么",
                    "thread_id": thread_id,
                },
            )
            body = r.json() if r.status_code == 200 else {}
            content = str(body.get("content") or "")
            ok("empty 如实转述", bool(_EMPTY_ACK_RE.search(content)), content[:80])
            ok("empty 不泄真题题号", not _QID_RE.search(content))

        r = await client.post("/api/history", headers=hdr_a, json={"thread_id": thread_id})
        if llm_ok:
            ok("history ok", r.status_code == 200, f"status={r.status_code}")
            msgs = (r.json() or {}).get("messages") or []
            ok("history 有消息", len(msgs) >= 2, f"n={len(msgs)}")
            types = [m.get("type") for m in msgs]
            ok("history 无 tool 气泡", "tool" not in types, f"types={types}")
        else:
            note(f"history 形态: status={r.status_code}（未造多轮，仅探针）")

        r = await client.get("/api/threads", headers=hdr_a)
        ok("threads ok", r.status_code == 200, f"status={r.status_code}")
        tids = [t.get("thread_id") for t in (r.json() or {}).get("threads") or []]
        if llm_ok:
            ok("threads 含当前会话", thread_id in tids, f"found={thread_id in tids}")
            r = await client.post("/api/history", headers=hdr_b, json={"thread_id": thread_id})
            ok("跨用户 history 被拒", r.status_code == 404, f"status={r.status_code}")
        else:
            r = await client.post("/api/history", headers=hdr_b, json={"thread_id": thread_id})
            note(f"跨用户/不存在 history: status={r.status_code}（期望 404）")
            ok("history 404 语义", r.status_code == 404, f"status={r.status_code}")

        # ── 3. SSE ──
        print("==== SSE stream ====")
        if not llm_ok:
            note("跳过 SSE（LLM 不可用）")
        else:
            async with client.stream(
                "POST",
                "/api/stream",
                headers=hdr_a,
                json={
                    "message": "BST 删除的双支结点怎么处理？",
                    "thread_id": thread_id,
                    "stream_tokens": True,
                },
            ) as resp:
                ok("stream status=200", resp.status_code == 200, f"status={resp.status_code}")
                ok(
                    "stream content-type",
                    "text/event-stream" in resp.headers.get("content-type", ""),
                )
                raw = ""
                async for chunk in resp.aiter_text():
                    raw += chunk

            events = parse_sse(raw)
            ok(
                "SSE 以 [DONE] 结尾",
                bool(events) and events[-1].get("type") == "_done",
                f"last={events[-1] if events else None}",
            )
            msg_events = [e for e in events if e.get("type") == "message"]
            tok_events = [e for e in events if e.get("type") == "token"]
            err_events = [e for e in events if e.get("type") == "error"]
            ok("SSE 无 error 事件", not err_events, f"errs={err_events[:1]}")
            ok(
                "SSE 有 message 或 token",
                bool(msg_events or tok_events),
                f"msg={len(msg_events)} tok={len(tok_events)}",
            )
            dirty = []
            empty_custom = 0
            for e in msg_events:
                c = e.get("content") or {}
                t = c.get("type")
                content = str(c.get("content") or "")
                if t == "tool":
                    dirty.append(("tool", c.get("name")))
                elif t == "custom":
                    if not (c.get("custom_data") or {}):
                        empty_custom += 1
                elif not content.strip():
                    dirty.append((t or "?", content[:40]))
            ok("SSE message 皆为可见对话", not dirty, f"dirty={dirty[:3]}")
            if empty_custom:
                note(f"custom 事件缺载荷 x{empty_custom}")
            n_custom = sum(
                1 for e in msg_events if (e.get("content") or {}).get("type") == "custom"
            )
            if n_custom:
                note(f"custom 事件 {n_custom} 个（docs/工作记忆，content 空属预期）")
            if tok_events:
                note(f"token 事件 {len(tok_events)} 个（stream_tokens=true）")

        # ── 4. 出题 / 批改 API ──
        print("==== questions generate / grade ====")
        if not llm_ok:
            note("跳过 questions（LLM 不可用）")
        else:
            r = await client.post(
                "/api/questions/generate",
                headers=hdr_a,
                json={"topic": "BST 删除", "count": 1, "difficulty": "mixed"},
            )
            ok("questions/generate", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                qs = (r.json() or {}).get("questions") or []
                ok("generate 有题目", len(qs) >= 1, f"n={len(qs)}")
                if qs:
                    ok(
                        "题目含题干+答案",
                        bool(qs[0].get("stem")) and bool(qs[0].get("standard_answer")),
                    )
            else:
                note(f"generate 失败体: {r.text[:160]}")

            r = await client.post(
                "/api/questions/grade",
                headers=hdr_a,
                json={
                    "stem": "进程死锁产生的四个必要条件是什么",
                    "user_answer": "互斥、占有并等待、不可剥夺、循环等待",
                },
            )
            ok("questions/grade", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                g = r.json() or {}
                ok(
                    "grade 有分数字段",
                    any(k in g for k in ("score", "total_score", "grade", "result")),
                    f"keys={list(g)[:8]}",
                )
            else:
                note(f"grade 失败体: {r.text[:160]}")

        # ── 5. 未知 agent ──
        print("==== 边界 ====")
        r = await client.post("/api/no_such_agent/invoke", headers=hdr_a, json={"message": "hi"})
        ok("未知 agent 404", r.status_code == 404, f"status={r.status_code}")

    print("\n==== 汇总 ====")
    if fails:
        print(f"SERVICE ACCEPTANCE FAIL {len(fails)}")
        for f in fails:
            print(" -", f)
        return 1
    print("SERVICE ACCEPTANCE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
