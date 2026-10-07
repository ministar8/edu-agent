"""Step 4 · harness 两缺口的最小 Gate（脚本级，**不跑 agent、零 LLM 成本**）。

验证交接文档 §8 Step 4 的两个硬要求**已经实现且行为正确**：

    缺口① 每 case 独立 user_id     → 不同 case 的 Store 数据互不污染
    缺口② 跑前清理该 user 的 Store → 起点干净，重跑不受上次残留影响

★ 本脚本**不调 LLM**，只对 ``scripts/agent_behavior_smoke.py`` 的两项能力做机械验证。
  agent 在新 thread 里**实际召回**（⑥b）需真跑 agent，属 Step 5，本脚本不验。

判据（全部可机械判定）：
    ① ``make_user_id`` 两次调用**不相等**（独立 + 重跑干净）
    ② 两个不同 case 的 user_id **不相等**（case 间隔离）
    ③ user_id 不含非法字符（可作命名空间段）
    ④ ``_cleanup_user_store`` 能删净 profile + episodes 两个命名空间
    ⑤ 清理**只影响目标 user**，不波及其他 user
    ⑥ 清理后 ``abuild_memory_card`` 返回空串（记忆真的没了）

用法::

    PYTHONPATH=src uv run python scripts/memory_step4_gate.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# 被测脚本：顶层只做 sys.path 注入，import 期不跑 LLM（零成本）。
# `type: ignore` 与 `task_eval.runner` 的同类导入一致（pyrefly 只扫 src/）。
from agent_behavior_smoke import (  # noqa: E402
    _cleanup_user_store,
    make_user_id,
)  # type: ignore[import-not-found]

from memory import initialize_store  # noqa: E402
from memory.namespaces import student_episodes_ns, student_profile_ns  # noqa: E402
from memory.profile import aget_profile  # noqa: E402
from memory.remember import record_grade  # noqa: E402
from memory.working import abuild_memory_card  # noqa: E402

_ok_all = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global _ok_all
    mark = "✅" if passed else "❌"
    if not passed:
        _ok_all = False
    print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))


async def _seed_two_cases(store) -> tuple[str, str]:
    """往两个独立 user **各写两条同一 KP 的 grade**，返回两个 user_id。

    用 ``record_grade`` 走**真实写入路径**（它内部会 normalize + 更新 profile），
    而不是手工 aput —— 保证 seed 与产品行为同源。

    ★ 为什么每 user 写 **2 条**：``compute_weak_topics`` 的判据是
      **同一标准 KP 累计 hits ≥ MEMORY_WEAK_MIN_HITS（默认 2）** 才计入 weak_topics。
      写 1 条只会留下 episode、不产生画像 —— 那就测不到「记忆卡非空」这一环。
    """
    uid_a = make_user_id("mem-001")
    uid_b = make_user_id("mem-002")
    for uid, kp in ((uid_a, "平衡二叉树"), (uid_b, "栈")):
        for i in range(2):  # 2 hits ⇒ 达到 weak 阈值
            await record_grade(
                user_id=uid,
                topic=f"{kp}-seed-{i}",
                score=30.0,
                error_analysis="测试种子",
                stem=f"关于{kp}的测试题干 {i}",
                knowledge_points=[kp],
            )
    return uid_a, uid_b


async def _count_ns(store, ns) -> int:
    items = await store.asearch(ns, limit=500)
    return len(items)


async def main() -> int:
    from memory.runtime import set_store

    print("=" * 70)
    print("缺口① 每 case 独立 user_id（make_user_id）")
    print("=" * 70)
    a1 = make_user_id("mem-001")
    a2 = make_user_id("mem-001")
    b1 = make_user_id("mem-002")
    check("同一 case 两次调用不相等（重跑干净）", a1 != a2, f"{a1} vs {a2}")
    check("不同 case 不相等（case 间隔离）", a1 != b1, f"{a1} vs {b1}")
    ok_charset = all(c.isalnum() or c in "-_" for c in a1)
    check("user_id 字符集合法（可作命名空间段）", ok_charset, a1)

    async with initialize_store() as store:
        # ★ 必须 set_store：`record_grade` 经 `get_store()` 取**进程级**引用，
        #   不 set 则 `_record_episode` 静默跳过（safe_remember 吞异常）→ seed 写不进去。
        #   这与 `service.lifespan` / `task_eval.runner` 的装配方式一致。
        set_store(store)
        print()
        print("=" * 70)
        print("缺口② 跑前清理该 user 的 Store（_cleanup_user_store）")
        print("=" * 70)
        uid_a, uid_b = await _seed_two_cases(store)
        print(f"  seed 完成：A={uid_a}  B={uid_b}")

        a_eps = await _count_ns(store, student_episodes_ns(uid_a))
        a_prof = await aget_profile(store, uid_a)
        b_eps = await _count_ns(store, student_episodes_ns(uid_b))
        check("④a seed 后 A 有 episode", a_eps >= 2, f"{a_eps} 条")
        check("④a seed 后 A 有画像", bool(a_prof.weak_topics), f"{a_prof.weak_topics}")

        card_before = await abuild_memory_card(store, uid_a)
        check("⑥ 清理前 A 的记忆卡非空", bool(card_before), repr(card_before[:60]))

        removed = await _cleanup_user_store(store, uid_a)
        print(f"  清理 A 删除 {removed} 项")

        a_eps_after = await _count_ns(store, student_episodes_ns(uid_a))
        a_prof_after = await aget_profile(store, uid_a)
        a_prof_items = await _count_ns(store, student_profile_ns(uid_a))
        check("④b 清理后 A 的 episode 清空", a_eps_after == 0, f"{a_eps_after} 条")
        check("④b 清理后 A 的画像清空", a_prof_items == 0, f"{a_prof_items} 条")
        check(
            "④b 清理后 A 的 weak_topics 为空",
            not a_prof_after.weak_topics,
            f"{a_prof_after.weak_topics}",
        )

        card_after = await abuild_memory_card(store, uid_a)
        check("⑥ 清理后 A 的记忆卡为空串", card_after == "", repr(card_after[:60]))

        # ⑤ 隔离性：清理 A 不得动 B
        b_eps_after = await _count_ns(store, student_episodes_ns(uid_b))
        b_prof_after = await aget_profile(store, uid_b)
        check("⑤ B 的 episode 未受影响", b_eps_after == b_eps == 2, f"{b_eps_after} 条")
        check(
            "⑤ B 的 weak_topics 未受影响",
            "栈" in b_prof_after.weak_topics,
            f"{b_prof_after.weak_topics}",
        )

        # 收尾：清掉 B，避免污染真实 store.db
        await _cleanup_user_store(store, uid_b)
        b_final = await _count_ns(store, student_episodes_ns(uid_b))
        check("收尾 B 已清空（不留脏数据）", b_final == 0, f"{b_final} 条")

    print()
    print("=" * 70)
    verdict = (
        "✅ STEP 4 GATE 通过 —— 两缺口已实现且行为正确" if _ok_all else "❌ STEP 4 GATE 未通过"
    )
    print(verdict)
    print("=" * 70)
    if _ok_all:
        print("★ 遗留：⑥b（agent 在新 thread 里实际召回）需真跑 agent，属 Step 5。")
    return 0 if _ok_all else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
