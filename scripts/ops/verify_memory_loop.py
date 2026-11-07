"""Memory 教学闭环完整验证（离线，真实 SQLite Store）。

与 ``verify_agent_chain.py`` 共用假模型装配（import 它即完成 ``get_model`` 补丁 +
真实编译图），本脚本聚焦「出题 → 批改 → 记忆更新 → 下一轮记忆卡读取」的闭环：

1. **M1 question episode 写入**：``generate_practice_questions`` 工具真实调
   ``record_question`` → Store（``("student", uid, "episodes")``），batch_id 回传模型。
2. **M2 grade episode 写入 + weak_topics 派生**：``grade_student_answer`` 工具真实调
   ``record_grade`` → episode 落库，且 grade episode **同步触发** ``a_recompute_weak_topics``
   ——两次低分（score<60、同 canonical KP）满足 ``MEMORY_WEAK_MIN_HITS=2`` 防抖后
   ``profile.weak_topics`` 变为 ["二叉排序树"]；此前为 []（1 hit 不进表，防抖生效）。
3. **M3 下一轮记忆卡读取**：同一 uid 再开一轮，``load_memory`` 读 Store 生成记忆卡
   SystemMessage（固定 id upsert）注入 state；读链四态通道记录 empty → success。
4. **M4 SQLite 持久化**：关闭第 1 个 Store 连接后**重开全新连接**读同一文件，
   episode/profile 原样读回 —— 只能来自磁盘（进程内无缓存）。
5. **M5 用户隔离**：另一 uid 的 namespace 完全为空；其高分组不会被拉薄别人；
   双向断言（她读不到 7001 的卡，7001 的薄表不受 7002 影响）。

Store 装配与 service lifespan 同口径：``set_store(store)``（图内 ``get_store()`` 取用）；
Store 文件用独立临时路径（``data/tmp/``），不碰产品 ``data/sqlite/store.db``。
向量索引关闭（``MEMORY_STORE_VECTOR_ENABLED=false``）—— 本验证聚焦闭环落库，
向量检索另有独立评测覆盖。

用法::

    $env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH="src"
    .venv\\Scripts\\python.exe scripts\\ops\\verify_memory_loop.py

退出码：0 = 全部通过；1 = 任一断言失败。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# 与 V 相同的防御性开关（必须在任何 src import 之前落环境变量）；
# Store 用独立临时文件、关向量索引 —— settings 在 V 的 import 期定格。
os.environ["USE_FAKE_MODEL"] = "true"
os.environ["USE_FAKE_EMBEDDING"] = "true"
os.environ["USE_FAKE_RERANK"] = "true"
os.environ["MEMORY_STORE_VECTOR_ENABLED"] = "false"
_STORE_DB = Path("data/tmp/verify_memory_store.db").resolve()
os.environ["SQLITE_STORE_PATH"] = str(_STORE_DB)

import verify_agent_chain as V  # noqa: E402  —— 副作用：补丁假模型 + 装配真实图
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from agents.orchestration.teaching_graph import (  # noqa: E402
    MEMORY_CARD_MESSAGE_ID,
    memory_read_statuses,
)
from core import settings  # noqa: E402
from memory.episodes import arecent_episodes  # noqa: E402
from memory.profile import aget_profile  # noqa: E402
from memory.runtime import set_store  # noqa: E402
from memory.sqlite import get_sqlite_store  # noqa: E402
from schema.grading import GradingResult  # noqa: E402

U1, U2 = "7001", "7002"
_KP_MAIN, _KP_OTHER = "二叉排序树", "哈夫曼编码"  # canonical 词表内的两个考点

_REPORT: list[tuple[str, bool, str]] = []


def check(section: str, ok: bool, detail: str) -> bool:
    _REPORT.append((section, bool(ok), detail))
    print(f"    {'✓' if ok else '✗'} {detail}", flush=True)
    return bool(ok)


def _config(thread: str, uid: str, batch_id: str = "") -> dict:
    """与 service 层同口径的 configurable（显式传齐，不指望回落补）。

    ★``_resolve_config`` 是「带 configurable 就整块采用」——少传 user_id 会让
    工具内的 episode 写入被**静默跳过**，这正是本验证要盯住的第一跳。
    """
    configurable: dict = {
        "thread_id": thread,
        "request_id": f"req-{thread}",
        "user_id": uid,
    }
    if batch_id:
        configurable["question_batch_id"] = batch_id
    return {
        "configurable": configurable,
        "recursion_limit": settings.AGENT_RECURSION_LIMIT,
    }


async def _run(query: str, thread: str, uid: str, batch_id: str = "") -> dict:
    return await V.edu_supervisor.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        _config(thread, uid, batch_id),
    )


def _route(agent: str, call_id: str):
    _MODELS = V._MODELS
    return _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": f"transfer_to_{agent}", "args": {}, "id": call_id}]
    )


def _turn_ok(state: dict, section: str, final) -> bool:
    ok = check(section, state.get("task_status") == "completed",
               f"task_status == completed（实际 {state.get('task_status')!r}）")
    tail = next(
        (m for m in reversed(state.get("messages") or [])
         if getattr(m, "type", None) == "ai"),
        None,
    )
    if final is not None:
        check(section,
              tail is not None and str(tail.content) == str(final.content),
              f"本轮有闭环终答（{getattr(tail, 'name', '?')}"
              f"：{str(tail.content)[:24] if tail else '无 AI 消息'}…）")
    V._MODELS["supervisor"].reset([])  # 防御：下轮必须复置脚本
    return ok


@contextlib.contextmanager
def grading_stub(score: float, kps: list[str]):
    """批改结构化核心替身：确定性分数（弱项聚合需要 <60，防清理需 ≥85）。"""

    async def _graded(
        messages,
        schema,
        *,
        temperature=None,
        timeout=None,
        stage=None,
        prompt_set_version=None,
        salvage=None,
    ):
        assert schema is GradingResult
        return GradingResult(
            score=score,
            feedback=("正确。" if score >= settings.MEMORY_GOOD_SCORE else "答案有误。"),
            is_wrong=score < 60.0,
            error_analysis="" if score >= 60 else "中序遍历与内序性理解有偏差。",
            knowledge_points=kps,
        )

    original = V.grading_mod.call_structured
    setattr(V.grading_mod, "call_structured", _graded)
    try:
        yield
    finally:
        setattr(V.grading_mod, "call_structured", original)


def _card_in(state: dict) -> str | None:
    cards = [m for m in (state.get("messages") or [])
             if isinstance(m, SystemMessage) and m.id == MEMORY_CARD_MESSAGE_ID]
    return str(cards[0].content) if cards else None


async def main_async() -> int:
    broke: list[str] = []
    batch_id_m1 = ""

    _STORE_DB.parent.mkdir(parents=True, exist_ok=True)
    _STORE_DB.unlink(missing_ok=True)  # 从零开始，episode 计数才可比

    async with get_sqlite_store() as store:
        set_store(store)

        # ── M1 question episode 写入 ─────────────────────────────────────
        try:
            S = "M1"
            print(f"\n[{S} question episode 写入] uid={U1} 出 2 道题（batch_id 应回传模型）")
            r1 = _route("question_agent", "call_m1")
            q1 = V._MODELS["question"].aim("以下是题目正文（脚本预置）。")
            V._MODELS["supervisor"].reset([r1])
            V._MODELS["question"].reset([
                V._MODELS["question"].aim("", tool_calls=[
                    {"name": "generate_practice_questions",
                     "args": {"topic": "平衡二叉树", "count": 2, "difficulty": "basic"},
                     "id": "call_m1_t"}]),
                q1,
            ])
            V._MODELS["knowledge"].reset([]), V._MODELS["grading"].reset([])

            with V.stubs("question_ok"):
                state = await _run("请出 2 道关于平衡二叉树的基础选择题", S, U1)
            _turn_ok(state, S, q1)

            eps = await arecent_episodes(store, U1, limit=settings.MEMORY_EPISODE_SCAN_LIMIT)
            check(S, len(eps) == 1, f"Store 里恰有 1 条 episode（实际 {len(eps)}）")
            ep = eps[0]
            check(S, ep.type == "question", f"episode.type == question（实际 {ep.type!r}）")
            check(S, ep.topic == "平衡二叉树",
                  "topic 归一后 = canonical「平衡二叉树」原样保留")
            check(S, ep.agent_path == "chat_question",
                  f"agent_path == chat_question（实际 {ep.agent_path!r}）")
            check(S, ep.thread_id == S, f"thread_id 记为来源会话（{S}）")
            check(S, ep.meta.get("count") == 2, "meta.count == 2（出题数量写入）")
            check(S, isinstance(ep.batch_id, str) and len(ep.batch_id) == 32,
                  f"batch_id = 32 位 hex（{ep.batch_id!r}）")
            batch_id_m1 = ep.batch_id
            check(S, V._MODELS["question"].saw_tool_text(batch_id_m1),
                  "batch_id 随工具回包到达模型（供后续批改外键关联）")
            check(S, _card_in(state) is None,
                  "M1 时画像为空 ⇒ 无记忆卡注入（空卡不产出的降级正确）")
            sid = memory_read_statuses()
            check(S, sid and sid[-1] == "empty",
                  f"读链四态通道记为 empty（(uid 提供了但无卡)：{sid}）")
        except Exception:  # noqa: BLE001
            broke.append("M1")
            import traceback
            traceback.print_exc()

        # ── M2 grade episode 写入 + weak_topics 派生（2-hit 防抖）─────────
        try:
            S = "M2"
            print(f"\n[{S} grade episode 写入] uid={U1} 两次低分批改 → weak_topics=[{_KP_MAIN}]")

            async def _one_grade(score: float, call_no: str) -> tuple[dict, object]:
                r = _route("grading_agent", f"call_m2_r{call_no}")
                g = V._MODELS["grading"].aim(f"评分：{int(score)}/100（脚本预置）")
                V._MODELS["supervisor"].reset([r])
                V._MODELS["grading"].reset([
                    V._MODELS["grading"].aim("", tool_calls=[
                        {"name": "grade_student_answer",
                         # stem 恰为 canonical 词 ⇒ 记忆卡锚点分支（题干截断 topic）可确定命中
                         "args": {"stem": "二叉排序树",
                                  "user_answer": "不是", "standard_answer": "是（升序定理）"},
                         "id": f"call_m2_t{call_no}"}]),
                    g,
                ])
                V._MODELS["knowledge"].reset([]), V._MODELS["question"].reset([])
                with grading_stub(score, [_KP_MAIN]):
                    with V.stubs("retrieve_ok"):
                        state = await _run(
                            f"帮我批改第 {call_no} 题作答：不是", S, U1,
                            batch_id=batch_id_m1,
                        )
                return state, g

            # 第 1 次低分：仅 1 hit，防抖不允许进薄表
            _turn_ok((await _one_grade(40.0, "a"))[0], S, None)
            profile = await aget_profile(store, U1)
            check(S, profile.weak_topics == [],
                  "第 1 次低分后 weak_topics == []（MEMORY_WEAK_MIN_HITS=2 防抖生效）")
            eps = await arecent_episodes(store, U1, limit=settings.MEMORY_EPISODE_SCAN_LIMIT)
            check(S, len(eps) == 2, f"已有 {len(eps)} 条 episode（1 出题 + 1 批改）")
            g1 = next(e for e in eps if e.type == "grade")
            check(S, abs((g1.score or 0) - 40.0) < 1e-9 and g1.knowledge_points == [_KP_MAIN],
                  "grade episode 分数/KP 落库正确（40.0 / 二叉排序树）")
            check(S, g1.batch_id == batch_id_m1,
                  f"grade.batch_id == M1 出题批（外键闭环：{g1.batch_id!r}）")
            check(S, g1.agent_path == "chat_grade", "grade.agent_path == chat_grade")

            # 第 2 次低分：累计 2 hit ⇒ 进入薄表
            _turn_ok((await _one_grade(55.0, "b"))[0], S, None)
            grades = [e for e in await arecent_episodes(store, U1, limit=50) if e.type == "grade"]
            check(S, len(grades) == 2 and abs((grades[0].score or 0) - 55.0) < 1e-9,
                  "第 2 条 grade episode 落库（55.0）")
            profile = await aget_profile(store, U1)
            check(S, profile.weak_topics == [_KP_MAIN],
                  f"weak_topics 派生 == ['{_KP_MAIN}']（2 hit 达标；实际 {profile.weak_topics!r}）")
        except Exception:  # noqa: BLE001
            broke.append("M2")
            import traceback
            traceback.print_exc()

        # ── M3 下一轮记忆卡读取（read 四态 empty → success）──────────────
        try:
            S = "M3"
            print(f"\n[{S} 下一轮记忆卡读取] 同一 uid 新一轮对话，load_memory 读出卡片"
                  "（SystemMessage id=edu_memory_card）")
            final = V._MODELS["supervisor"].aim(
                "根据你的薄弱点（二叉排序树），建议先重做中序遍历相关题。"
            )  # 直答不进专家，卡片注入发生在 load_memory
            V._MODELS["supervisor"].reset([final])
            V._MODELS["knowledge"].reset([]), V._MODELS["question"].reset([])
            V._MODELS["grading"].reset([])

            n_before = len(memory_read_statuses())
            state = await _run("我下一步怎么复习？", S, U1)
            _turn_ok(state, S, final)

            card = _card_in(state)
            check(S, card is not None and "【学生记忆】" in (card or ""),
                  f"记忆卡注入 state（id={MEMORY_CARD_MESSAGE_ID}）")
            check(S, "薄弱：二叉排序树（最近55分，「二叉排序树」）" in (card or ""),
                  f"卡片薄弱行 = KP + 最近分 + 题干锚点：{(card or '')!r}")
            sid = memory_read_statuses()[n_before:]
            check(S, sid == ["success"],
                  f"读链四态通道本轮记为 success（empty → success 全链可观测：{sid}）")
        except Exception:  # noqa: BLE001
            broke.append("M3")
            import traceback
            traceback.print_exc()

    # store 第 1 个连接已关闭；从同一文件重开全新连接（进程内无缓存）
    async with get_sqlite_store() as store2:
        set_store(store2)

        # ── M4 SQLite 持久化（跨连接磁盘恢复）─────────────────────────────
        try:
            S = "M4"
            print(f"\n[{S} SQLite 持久化] 连接已关、重开新连接读同一文件")
            eps = await arecent_episodes(store2, U1, limit=50)
            types = sorted(e.type for e in eps)
            scores = sorted((e.score or 0) for e in eps if e.type == "grade")
            check(S, len(eps) == 3 and types == ["grade", "grade", "question"],
                  f"磁盘上 3 条 episode 原样读回（types={types}）")
            check(S, scores == [40.0, 55.0], f"两条低分批改分数完整（{scores}）")
            q_eps = [e for e in eps if e.type == "question"]
            check(S, q_eps and q_eps[0].batch_id == batch_id_m1,
                  "出题 episode 的 batch_id 跨连接存活")
            profile = await aget_profile(store2, U1)
            check(S, profile.weak_topics == [_KP_MAIN],
                  f"profile（含 weak_topics）持久化（{profile.weak_topics!r}）")
        except Exception:  # noqa: BLE001
            broke.append("M4")
            import traceback
            traceback.print_exc()

        # ── M5 用户隔离（写读两侧）───────────────────────────────────────
        try:
            S = "M5"
            print(f"\n[{S} 用户隔离] uid={U2} 空 namespace；高分组不回流；互不影响")
            check(S, await arecent_episodes(store2, U2, limit=50) == [],
                  "新用户 episode namespace 为空")
            check(S, (await aget_profile(store2, U2)).weak_topics == [],
                  "新用户 profile 为空画像")

            r = _route("grading_agent", "call_m5_r")
            g = V._MODELS["grading"].aim("评分：92/100（脚本预置）")
            V._MODELS["supervisor"].reset([r])
            V._MODELS["grading"].reset([
                V._MODELS["grading"].aim("", tool_calls=[
                    {"name": "grade_student_answer",
                     "args": {"stem": "判断：哈夫曼编码是最优前缀编码", "user_answer": "是",
                              "standard_answer": "是"},
                     "id": "call_m5_t"}]),
                g,
            ])
            V._MODELS["knowledge"].reset([]), V._MODELS["question"].reset([])
            with grading_stub(92.0, [_KP_OTHER]):
                with V.stubs("retrieve_ok"):
                    state5 = await _run("帮我批改哈夫曼题", S, U2)
            _turn_ok(state5, S, g)

            eps2 = await arecent_episodes(store2, U2, limit=50)
            check(S, len(eps2) == 1 and eps2[0].type == "grade",
                  f"U2 自己只见到自己的 1 条 grade（{len(eps2)} 条）")
            profile2 = await aget_profile(store2, U2)
            check(S, profile2.weak_topics == [],
                  "92 分 ≥ MEMORY_GOOD_SCORE ⇒ U2 自身 weak_topics 仍为空")
            _ = uuid.UUID(int=0).hex  # uuid 可用性冒烟（写链用 uuid 生成 key）

            eps1 = await arecent_episodes(store2, U1, limit=50)
            profile1 = await aget_profile(store2, U1)
            check(S, len(eps1) == 3 and profile1.weak_topics == [_KP_MAIN],
                  "U1 的 3 条 episode 与薄表完全未被 U2 影响（隔离双向成立）")

            # 读侧隔离：U2 的下一轮不应有 U1 的卡
            final2 = V._MODELS["supervisor"].aim("这是给你的复习建议（无 U1 内容）。")
            V._MODELS["supervisor"].reset([final2])
            state5b = await _run("我该怎么复习？", f"{S}b", U2)
            _turn_ok(state5b, S, final2)
            check(S, _card_in(state5b) is None,
                  "U2 的记忆卡通道为空（没有 U1 的薄弱行串台）")
        except Exception:  # noqa: BLE001
            broke.append("M5")
            import traceback
            traceback.print_exc()

    set_store(None)  # 与 service 关停同口径：进程级引用置 None

    print("\n" + "=" * 72)
    failures = [(s, d) for (s, ok, d) in _REPORT if not ok]
    for name in broke:
        failures.append((name, "场景执行期抛出未预期异常"))
    if failures:
        print(f"内存闭环 FAIL：{len(failures)} 条断言未通过")
        for s, d in failures:
            print(f"  - [{s}] {d}")
        return 1
    print("验证 PASS：Memory 教学闭环五场景全部通过")
    print(f"  M1 question episode 写入 ✓ · M2 grade episode + weak_topics ✓"
          f" · M3 记忆卡读取 ✓ · M4 SQLite 持久化 ✓ · M5 用户隔离 ✓"
          f"（全链落库经真实 SQLite Store：{_STORE_DB.name}，验证后清理）")
    _STORE_DB.unlink(missing_ok=True)  # 验证产物不留仓库
    return 0


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
