"""真实 invoke/stream 对话回归（走 edu_supervisor 图，与 service 同构）。

多轮：
  1) 「什么是二叉树的中序遍历？」
  2) 「给我一道 BST 删除的练习题」
  3) 「我的答案是 C」

断言：
  - ainvoke / astream 不抛错
  - 多轮后 context_mode 符合 Classifier
  - 返回含 messages

用法：
    USE_FAKE_MODEL=true uv run python scripts/e2e_invoke_stream.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_core.runnables import RunnableConfig  # noqa: E402

from agents.agents import DEFAULT_AGENT, get_agent  # noqa: E402
from agents.task_context import get_context_mode  # noqa: E402


async def invoke_turn(agent, message: str, thread_id: str) -> tuple[list, str | None]:
    config = RunnableConfig(configurable={"thread_id": thread_id, "user_id": "e2e"})
    events = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
        stream_mode=["updates", "values"],
    )
    last = events[-1] if events else (None, None)
    _type, response = last
    msgs = []
    if isinstance(response, dict):
        msgs = response.get("messages") or []
    return msgs, get_context_mode(thread_id=thread_id)


async def stream_turn(agent, message: str, thread_id: str) -> int:
    config = RunnableConfig(configurable={"thread_id": thread_id, "user_id": "e2e"})
    n = 0
    async for _event in agent.astream(
        {"messages": [HumanMessage(content=message)]},
        config=config,
        stream_mode=["updates", "messages", "custom"],
        subgraphs=True,
    ):
        n += 1
    return n


async def main() -> int:
    fails: list[str] = []
    agent = get_agent(DEFAULT_AGENT)
    thread = "thread-e2e-invoke"

    print("==== invoke turns ====")
    turns = [
        ("什么是二叉树的中序遍历？", {"learn", "method"}),
        ("给我一道 BST 删除的练习题", {"practice"}),
        ("我的答案是 C", {"grade"}),
    ]
    for msg, want in turns:
        try:
            msgs, mode = await invoke_turn(agent, msg, thread)
        except Exception as e:
            print(f"  INVOKE FAIL {msg!r}: {e}")
            fails.append(f"invoke {msg!r}")
            continue
        ok = mode in want if mode else False
        print(f"  {msg!r} -> mode={mode} msgs={len(msgs)} {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"mode {msg!r}: got {mode} want {want}")
        if not msgs:
            fails.append(f"empty messages {msg!r}")

    print("==== stream turn ====")
    try:
        n = await stream_turn(agent, "BST 删除怎么做？", "thread-e2e-stream")
        print(f"  stream events={n}")
        if n <= 0:
            fails.append("stream produced no events")
    except Exception as e:
        print(f"  STREAM FAIL: {e}")
        fails.append("stream")

    if fails:
        print("INVOKE/STREAM FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("INVOKE/STREAM PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
