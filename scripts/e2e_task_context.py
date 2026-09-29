"""多轮 context_mode 贯通测试（LangGraph / Store / ContextVar）。

场景：
  轮1 practice「给我一道 BST 练习题」
  轮2 「我的答案是 C」→ 应进入 grade（context=practice + 作答）

用法：
    uv run python scripts/e2e_task_context.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.task_context import (  # noqa: E402
    get_context_mode,
    load_thread_context,
    remember_query_mode,
    set_context_mode,
)
from rag.retrieval_policy import classify_task_mode  # noqa: E402


def main() -> int:
    fails = []
    print("==== multi-turn context_mode ====")

    # 模拟线程 T1：practice → 作答 → grade
    tid = "thread-e2e-ctx"
    set_context_mode(None)
    m1 = remember_query_mode("给我一道 BST 删除的练习题", thread_id=tid)
    print(f"  turn1: {m1}")
    if m1 != "practice":
        fails.append(f"turn1 want practice got {m1}")

    m2 = remember_query_mode("我的答案是 C", thread_id=tid)
    print(f"  turn2: {m2} (expect grade)")
    if m2 != "grade":
        fails.append(f"turn2 want grade got {m2}")

    # 显式 explain 压过 context
    m3 = remember_query_mode("2019-Q2 为什么选 B？", thread_id=tid)
    print(f"  turn3: {m3} (expect explain)")
    if m3 != "explain":
        fails.append(f"turn3 want explain got {m3}")

    # 新线程无 context → 默认
    set_context_mode(None)
    m4 = remember_query_mode("什么是死锁？", thread_id="thread-new")
    print(f"  new-thread: {m4} (expect learn)")
    if m4 != "learn":
        fails.append(f"new-thread want learn got {m4}")

    # 持久化：清 ContextVar 后 load_thread_context
    set_context_mode(None)
    if get_context_mode() is not None:
        # 其它线程残留则清空
        set_context_mode(None)
    loaded = load_thread_context(tid)
    print(f"  reload thread-e2e-ctx: {loaded}")
    if loaded != "explain":
        fails.append(f"reload want explain got {loaded}")

    # tools 路径：get_context_mode 可见
    cm = get_context_mode()
    print(f"  get_context_mode: {cm}")
    if cm != "explain":
        fails.append(f"get_context_mode want explain got {cm}")

    # classify 纯函数
    if classify_task_mode("我的答案是 C", context_mode="practice") != "grade":
        fails.append("classify context practice+answer")

    if fails:
        print("CONTEXT CHAIN FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("CONTEXT CHAIN PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
