"""Step 2 · Memory 最小链路 Gate（脚本级，**不改 harness**）。

验证链路（Part 7 的 Step 3 检查点 ①~⑤ + ⑥a）：

    agrade_answer → ① result.knowledge_points
                  → ② record_grade（内部 normalize_topics）
                  → ③ Episode.knowledge_points（Store）
                  → ④ compute_weak_topics(allow_legacy_fallback=False)
                  → ⑤ profile.weak_topics（Store）
                  → ⑥a abuild_memory_card → 记忆卡

★ 本脚本**不跑 agent**，因此**不验证** ⑥b（agent 在新 thread 里实际召回）——
  那需要 harness 支持多段会话，属 Step 4/5。

★ Gate 纪律：任一层不通过 ⇒ **链路不通**，**不得**解释成「Memory 能力失败」。
  尤其：若某题 score ≥ 60（`MEMORY_WEAK_SCORE`）⇒ **该 case 不成立**，换错答方式重来。

用法::

    PYTHONPATH=src uv run python scripts/memory_step2_gate.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from memory import initialize_store  # noqa: E402
from memory.namespaces import student_episodes_ns, student_profile_ns  # noqa: E402
from memory.profile import aget_profile  # noqa: E402
from memory.remember import record_grade  # noqa: E402
from memory.topics import normalize_topic  # noqa: E402
from memory.weak_topics import compute_weak_topics  # noqa: E402
from memory.working import abuild_memory_card  # noqa: E402
from schema.grading import GradingResult  # noqa: E402

USER_ID = "eval-step2"
# ★ 期望考点名 = **KB 的规范考点名**，不是从 LLM 输出反推的。
#   依据：`kp_index['ds.tree.avl']['name'] == '平衡二叉树'`；
#   教材正文 `knowledge/basic/data_structure/06_tree.md` 中「平衡二叉树」出现 4 次、
#   「AVL 树」仅 1 次 ⇒ 规范名取「平衡二叉树」。
#   （初版误写为「AVL树」，导致 gate 假失败 —— 属 **gold 写错**，不是链路问题。）
EXPECTED_KP = "平衡二叉树"

# ── 两道 AVL 真题（同一标准 KP：ds.tree.avl）────────────────────────
# 2012-Q4：正解 B(20)，学生错选 D(33)
Q_A = {
    "qid": "2012-Q4",
    "stem": (
        "若平衡二叉树的高度为 6，且所有非叶结点的平衡因子均为 1，"
        "则该平衡二叉树的结点总数为 。\n"
        "A. 10\nB. 20\nC. 32\nD. 33"
    ),
    "standard_answer": "B. 20",
    "user_answer": "我选 D（33）",
}
# 2013-Q3：正解 D(3)，学生错选 A(0)
Q_B = {
    "qid": "2013-Q3",
    "stem": (
        "若将关键字 1, 2, 3, 4, 5, 6, 7 依次插入到初始为空的平衡二叉树 T 中，"
        "则 T 中平衡因子为 0 的分支结点的个数是 。\n"
        "A. 0\nB. 1\nC. 2\nD. 3"
    ),
    "standard_answer": "D. 3",
    "user_answer": "我选 A（0）",
}

_ok_all = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global _ok_all
    mark = "✅" if passed else "❌"
    if not passed:
        _ok_all = False
    print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))


async def _cleanup(store) -> None:
    """跑前清理该 user 的 Store 数据（保证起点干净）。"""
    for ns in (student_profile_ns(USER_ID), student_episodes_ns(USER_ID)):
        try:
            items = await store.asearch(ns, limit=200)
            for it in items:
                await store.adelete(ns, it.key)
        except Exception as exc:  # noqa: BLE001
            print(f"    （清理 {ns} 时忽略：{type(exc).__name__}）")


async def main() -> int:
    from agents.grading_core import agrade_answer
    from memory.runtime import set_store

    async with initialize_store() as store:
        set_store(store)
        await _cleanup(store)

        print("=" * 70)
        print("① 批改 → result.knowledge_points")
        print("=" * 70)
        results: list[GradingResult] = []
        for tag, q in (("A", Q_A), ("B", Q_B)):
            r = await agrade_answer(
                stem=q["stem"], user_answer=q["user_answer"], standard_answer=q["standard_answer"]
            )
            results.append(r)
            kps = [normalize_topic(k) for k in r.knowledge_points]
            print(f"  题 {tag}（{q['qid']}）: score={r.score}  KP={r.knowledge_points}")
            check(f"题 {tag} score < 60", r.score < 60, f"score={r.score}")
            check(f"题 {tag} KP 非空", bool(kps), f"normalize 后={kps}")
            check(f"题 {tag} KP 含「{EXPECTED_KP}」", EXPECTED_KP in kps, f"{kps}")

        print()
        print("=" * 70)
        print("② record_grade → ③ Episode.knowledge_points（Store）")
        print("=" * 70)
        for tag, q, r in zip("AB", (Q_A, Q_B), results, strict=True):
            eid = await record_grade(
                user_id=USER_ID,
                topic=q["stem"][:80],  # legacy 字段，不参与 Memory 语义
                score=float(r.score),
                error_analysis=r.error_analysis or "",
                stem=q["stem"],
                knowledge_points=r.knowledge_points,
            )
            print(f"  题 {tag}: episode_id={eid}")

        eps = await store.asearch(student_episodes_ns(USER_ID), limit=50)
        grades = []
        for it in eps:
            val = it.value
            if isinstance(val, bytes):
                val = json.loads(val.decode("utf-8"))
            grades.append(val)
        n_with_kp = sum(1 for g in grades if g.get("knowledge_points"))
        print(f"  Store 里 grade episodes: {len(grades)} 条，其中有 KP 的 {n_with_kp} 条")
        check(
            "③ 每条 episode 的 knowledge_points 非空",
            n_with_kp == len(grades) == 2,
            f"{n_with_kp}/{len(grades)}",
        )

        print()
        print("=" * 70)
        print("④ compute_weak_topics（allow_legacy_fallback=False）")
        print("=" * 70)
        from memory.schemas import Episode

        ep_objs = [Episode(**g) for g in grades]
        weak = compute_weak_topics(ep_objs, allow_legacy_fallback=False)
        print(f"  weak_topics = {weak}")
        check(f"④ weak_topics 含「{EXPECTED_KP}」", EXPECTED_KP in weak, f"{weak}")

        print()
        print("=" * 70)
        print("⑤ profile.weak_topics（Store）")
        print("=" * 70)
        profile = await aget_profile(store, USER_ID)
        print(f"  profile.weak_topics = {profile.weak_topics}")
        check(
            f"⑤ Store 的 weak_topics 含「{EXPECTED_KP}」",
            EXPECTED_KP in profile.weak_topics,
            f"{profile.weak_topics}",
        )

        print()
        print("=" * 70)
        print("⑥a 记忆卡（abuild_memory_card）—— Store → 记忆卡")
        print("=" * 70)
        card = await abuild_memory_card(store, USER_ID)
        print("  ---- 记忆卡内容 ----")
        print("  " + (card.replace("\n", "\n  ") if card else "（空）"))
        print("  --------------------")
        check(f"⑥a 记忆卡非空且含「{EXPECTED_KP}」", bool(card) and EXPECTED_KP in card)

    print()
    print("=" * 70)
    verdict = "✅ GATE 通过 —— 产品链完整" if _ok_all else "❌ GATE 未通过 —— 链路有断点"
    print(verdict)
    print("=" * 70)
    if not _ok_all:
        print("★ 注意：这是**链路问题**（产品/脚本），不是「Memory 能力失败」。")
        print("  尤其若某题 score ≥ 60 ⇒ 该 case 不成立，应换错答方式。")
    else:
        print("★ ⑥b（agent 在新 thread 里实际召回）仍需 harness 支持多段会话，属 Step 4/5。")
    return 0 if _ok_all else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
