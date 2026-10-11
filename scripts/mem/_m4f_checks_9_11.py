"""memory_step4fix_gate 判据组：⑨ 批改抗格式飘移 / ⑩ context-fallback / ⑪ topic 归一

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap

from _m4f_core import check, section


def check_9() -> None:
    """⑨ 批改链路抗格式飘移（2026-10-06 Step 5 实测缺陷 A 的回归护栏）。

    实测缺陷：模型在 function_calling 下偶发返回裸文本/带工具标记的文本，
    此前因 `feedback` 超 `max_length` 直接 `ValidationError` ⇒ 整次批改硬失败
    （修复前 ON 组 **5/9 = 55.6%**；分母 = A 段**预期**批改次数，失败含「分数不可解析」与
    「完全无落分记录」两种形态。旧记「62.5% = 5/8」的分母 8 无法从归档构造，
    见 `docs/EXPERIMENTS.md` §20.3）。三处修复必须都在位：
      ⑨a schema 超长**截断**而非拒绝
      ⑨b 真错误（score 越界 / 缺字段）**仍被拒绝**
      ⑨c 工具标记可被清洗
      ⑨d 兜底能从裸文本/含标记 JSON 重建对象（**全字段**断言，不只看 score）
      ⑨e `call_structured` 有重试且超时不重试
      ⑨f 超时不重试（AST 静态检查）
      ⑨g KV 白名单覆盖 schema 全部字段（第二轮 review 新增）
      ⑨h 首行有前言/空行仍能解析（防 D2-2 回归）
      ⑨i is_wrong 不被非 key 行污染（防 D2-1 语义反转回归）
      ⑨j/k 多行字段可续行 + list 字段按分隔符切分
    """
    section("⑨ 批改链路抗格式飘移")
    _c9_truncate()
    _c9_reject()
    _c9_strip()
    _c9_salvage()
    _c9_kv_fields()
    _c9_parsers()
    _c9_retry()


async def check_10() -> None:
    """⑩ context-fallback 接线（2026-10-06 Step 5 实测第二个真实缺陷）。

    实测：LangChain **不**把运行时 ``RunnableConfig`` 注入工具函数参数，故工具里
    ``uid = user_id_from_config(config)`` 恒为 ``None`` ⇒ ``record_grade`` 的
    ``if uid:`` 分支被静默跳过 ⇒ 批改成功却 **EPISODES=0** ⇒ ``weak_topics`` 恒空
    ⇒ 跨会话永不召回。这是"成功但没落库"型缺陷，工具输出完全正常，极难发现。

    本节**零 LLM 成本**地验证修复：
      ⑩a 显式 config 优先（不破坏既有调用方）
      ⑩b 无显式 config 时回落运行时上下文（`ensure_config` 语义）
      ⑩c 无上下文时不抛错（直接单测场景）
      ⑩d 真写一条 episode 后 `weak_topics` 能派生（链路端到端）
    """
    section("⑩ context-fallback（工具 config 注入缺陷的修复）")
    _c10_config()
    await _c10_runtime()
    await _c10_episodes()
    await _c10_isolation()
    _c10_contract()


def check_11() -> None:
    """⑪ `normalize_topic` 不得改坏 canonical name（2026-10-06 Step 5 实测缺陷 D）。

    `normalize_topic` 是 Memory 写入 / 派生的**唯一入口**：
        Episode.knowledge_points ← normalize_topics(模型输出)
        模型输出 → normalize_topic → 与 kp_index 的 canonical name 做相等匹配

    修复前的两个破坏路径：
      ① `_WS.sub("", text)` 删掉全部空白 ⇒ 21 个**含空格**的 canonical 名被改写
         （`TCP 流量控制` → `TCP流量控制`），聚合从此永久错配；
      ② `_TOPIC_ALIASES` 的**目标值不是 canonical** ⇒ 归一后落到**不可达值**，
         共两例：`页面置换算法 → 页面置换`（canonical 改成非 canonical）、
                 `deadlock → 进程死锁`（kp_index 里根本没有「进程死锁」，只有「死锁」）。

    判据（全部机械）：
      ⑪a 162 个 canonical 经 `normalize_topic` **恒等**（0 破坏）
      ⑪b 含空格的 canonical 不被去空格
      ⑪c 别名表中**目标 canonical** 的条目仍被正确纠正
      ⑪d **反向映射必须被拦住**（canonical 名不得被 rag 同义词表改写成别的值）
      ⑪e 写入路径 `normalize_topics` 保序去重且结果全 canonical
      ⑪f **全表断言**：`_TOPIC_ALIASES` 的**每一条 target 都必须 ∈ canonical**
          —— 这是 `deadlock → 进程死锁` 漏检后的补丁。⑪c 只测样本，故漏掉了它。
    """
    section("⑪ normalize_topic 不得改坏 canonical name")
    _c11_canonical()
    _c11_aliases()
    _c11_reverse()
    _c11_batch()


def _c9_truncate() -> None:
    from schema.grading import GradingResult

    # ⑨a 截断
    r = GradingResult.model_validate({"score": 40, "feedback": "字" * 2000, "is_wrong": True})
    check(
        "⑨a 超长 feedback **截断**而非拒绝（不再整次硬失败）",
        len(r.feedback) == 800,
        str(len(r.feedback)),
    )
    r2 = GradingResult.model_validate({"score": 40, "is_wrong": True})
    check("⑨a' feedback 可缺省（默认空串）", r2.feedback == "")


def _c9_reject() -> None:
    from pydantic import ValidationError

    from schema.grading import GradingResult

    # ⑨b 真错误仍拒绝
    rejected = 0
    for bad in (
        {"score": 150, "feedback": "x", "is_wrong": True},
        {"score": -1, "feedback": "x", "is_wrong": True},
        {"feedback": "x", "is_wrong": True},
        {"score": 40, "feedback": "x"},
    ):
        try:
            GradingResult.model_validate(bad)
        except ValidationError:
            rejected += 1
    check("⑨b 真错误（越界/缺必填）**仍被拒绝**", rejected == 4, f"{rejected}/4")


def _c9_strip() -> None:
    from rag.retrieval.llm_calls import _strip_tool_markup as S

    # ⑨c 标记清洗

    cases = [
        ("a<parameter=score>b", "ab"),
        ("x\n<tool_call>\ny", "x\n\ny"),
        ("<function_call>{}</function_call>", "{}"),
        ("正文无标记", "正文无标记"),
        ("泛型 <T> 保留", "泛型 <T> 保留"),
    ]
    ok = sum(1 for src, want in cases if S(src) == want)
    check("⑨c 工具标记清洗正确且不误伤普通尖括号", ok == len(cases), f"{ok}/{len(cases)}")


def _c9_salvage() -> None:
    from rag.retrieval.llm_calls import _salvage_from_raw
    from schema.grading import GradingResult

    # ⑨d 兜底重建
    #   ★ 第二轮 review 补强：原来只断言 `score`，导致 D2-1（is_wrong 反转）/
    #     D2-3（KP 丢失）**都不会变红**。现改为断言**全部已解析字段**。

    kv = "score: 40\nfeedback: 反馈<parameter=x>ok\nis_wrong: true"
    r3 = _salvage_from_raw(kv, GradingResult, "gate")
    check("⑨d 裸文本+标记 ⇒ 兜底重建成功", r3 is not None and r3.score == 40)
    check(
        "⑨d-全字段 兜底结果**每个字段**都正确（不只 score）",
        r3 is not None and r3.score == 40 and r3.is_wrong is True and "ok" in r3.feedback,
        f"score={getattr(r3, 'score', None)} is_wrong={getattr(r3, 'is_wrong', None)}",
    )
    check(
        "⑨d' 无标记 ⇒ 不兜底（交回原逻辑）",
        _salvage_from_raw("score: 40\nfeedback: ok\nis_wrong: true", GradingResult, "gate") is None,
    )
    check(
        "⑨d'' 有标记但缺必填 ⇒ 兜底**不**硬凑（拒绝）",
        _salvage_from_raw("feedback: a<parameter=x>b", GradingResult, "gate") is None,
    )


def _c9_kv_fields() -> None:
    from rag.retrieval.llm_calls import _KV_ALL_FIELDS
    from schema.grading import GradingResult

    # ── ⑨g/h/i：第二轮 review 新增（针对裸文本 KV 解析的三个缺陷）──────────

    # ⑨g 协议一致性：KV 白名单必须**覆盖 schema 全部字段**。
    #   漏一个 ⇒ 该字段走 schema 默认值被静默丢弃（D2-3 的根因）。
    schema_fields = set(GradingResult.model_fields)
    missing = sorted(schema_fields - _KV_ALL_FIELDS)
    check(
        "⑨g KV 白名单覆盖 schema 全部字段（漏字段 ⇒ 静默丢失）",
        not missing,
        f"schema {len(schema_fields)} 个，缺失: {missing}"
        if missing
        else f"schema {len(schema_fields)} 个全覆盖",
    )


def _c9_parsers() -> None:
    from rag.retrieval.llm_calls import _try_kv_dict

    # ⑨h 首行有前言/空行 ⇒ 仍应从第一个合法 key 起解析（D2-2 回归防护）
    preambles = [
        "好的，批改如下：\nscore: 40\nis_wrong: true",
        "Let me grade this.\nscore: 40\nis_wrong: true",
        "\n\nscore: 40\nis_wrong: true",
    ]
    h_bad = [p for p in preambles if (_try_kv_dict(p) or {}).get("score") != 40]
    check("⑨h 首行前言/空行 ⇒ 仍解析出 score（不再全盘放弃）", not h_bad, f"失败: {len(h_bad)}")

    # ⑨i is_wrong 不得被「后续非 key 行」污染（D2-1 回归防护）
    pollution = [
        "score: 55\nis_wrong: true\ntopic: 平衡二叉树",
        "score: 55\nis_wrong: true\n知识点: 平衡二叉树",
        "score: 55\nis_wrong: true\nreason: 概念混淆",
        "score: 55\nis_wrong: true\n# 备注",
    ]
    i_bad = [p for p in pollution if (_try_kv_dict(p) or {}).get("is_wrong") is not True]
    check(
        "⑨i is_wrong 不被后续非 key 行污染（防语义反转）",
        not i_bad,
        f"被污染: {len(i_bad)} 例",
    )

    # ⑨j 多行字段仍可续行（feedback / error_analysis），且 list 字段按分隔符切分
    kv_multi = _try_kv_dict("score: 40\nfeedback: 第一行\n第二行\nis_wrong: true")
    check(
        "⑨j feedback 多行续行仍生效（且不污染 is_wrong）",
        kv_multi is not None
        and kv_multi.get("feedback") == "第一行\n第二行"
        and kv_multi.get("is_wrong") is True,
    )
    kv_list = _try_kv_dict("score: 40\nis_wrong: true\nknowledge_points: 平衡二叉树、二叉排序树")
    check(
        "⑨k knowledge_points 按 list 解析（非硬塞字符串）",
        isinstance((kv_list or {}).get("knowledge_points"), list)
        and (kv_list or {}).get("knowledge_points") == ["平衡二叉树", "二叉排序树"],
    )


def _c9_retry() -> None:
    import rag.retrieval.llm_calls as L
    from core.settings import settings as _s

    # ⑨e 重试接线

    check(
        "⑨e STRUCTURED_OUTPUT_RETRIES 存在且 ≥1（默认开重试）",
        int(_s.STRUCTURED_OUTPUT_RETRIES) >= 1,
        str(_s.STRUCTURED_OUTPUT_RETRIES),
    )

    # ★ 按事实修订：重试循环（含 `TimeoutError ⇒ break`）下沉到 `_structured_attempts`，
    #   断言原意（超时不重试，避免成倍放大延迟）不变。
    src = inspect.getsource(L._structured_attempts)
    tree = ast.parse(textwrap.dedent(src))
    has_timeout_break = any(
        isinstance(n, ast.If)
        and "TimeoutError" in ast.unparse(n.test)
        and any(isinstance(s, ast.Break) for s in n.body)
        for n in ast.walk(tree)
    )
    check("⑨f 超时**不**重试（避免成倍放大延迟）", has_timeout_break)


def _c11_canonical() -> None:
    from memory.topics import canonical_names, normalize_topic

    canonical = canonical_names()
    check("⑪a' canonical 集合可加载", len(canonical) > 100, f"{len(canonical)} 个")

    broken = sorted(n for n in canonical if normalize_topic(n) != n)
    check(
        "⑪a 全部 canonical 经 normalize_topic 恒等（0 破坏）",
        not broken,
        f"被改坏: {len(broken)} / {len(canonical)}" + (f" → {broken[:5]}" if broken else ""),
    )

    spaced = sorted(n for n in canonical if " " in n or "　" in n)
    spaced_broken = sorted(n for n in spaced if normalize_topic(n) != n)
    check(
        "⑪b 含空格的 canonical 不被去空格",
        bool(spaced) and not spaced_broken,
        f"{len(spaced)} 个含空格" + (f"，破坏: {spaced_broken}" if spaced_broken else ""),
    )


def _c11_aliases() -> None:
    from memory.topics import _TOPIC_ALIASES, canonical_names, normalize_topic

    canonical = canonical_names()
    # ⑪c 别名表条目：逐个核验「键非 canonical 的条目」归一后确实到 canonical。
    #   ★ 注意：`AVL树` **不在** `_TOPIC_ALIASES` 里（它靠 rag 兜底 ③ 命中），
    #     故不能拿它当「别名表覆盖」的样本 —— 这里分开测，避免再次归因错误。
    alias_entries = {k: v for k, v in _TOPIC_ALIASES.items() if k not in canonical}
    alias_bad = [
        (k, normalize_topic(k), v)
        for k, v in alias_entries.items()
        if normalize_topic(k) != v or v not in canonical
    ]
    check(
        "⑪c 别名表条目归一后均到 canonical",
        bool(alias_entries) and not alias_bad,
        f"{len(alias_entries)} 条非 canonical 键" + (f"，错误: {alias_bad}" if alias_bad else ""),
    )

    # ⑪f ★ 全表断言：`_TOPIC_ALIASES` 的**每一条 target** 必须 ∈ canonical。
    #   这条是 `deadlock → 进程死锁` 漏检（⑪c 只测样本）后的补丁：
    #   任何「指向不存在考点」的别名都会**永久不命中**，且不报错，必须机械拦下。
    bad_targets = sorted(f"{k!r} → {v!r}" for k, v in _TOPIC_ALIASES.items() if v not in canonical)
    check(
        "⑪f **_TOPIC_ALIASES 每条 target 均 ∈ canonical**（不可达目标值 ⇒ 红）",
        not bad_targets,
        f"全表 {len(_TOPIC_ALIASES)} 条" + (f"，不可达: {bad_targets}" if bad_targets else ""),
    )

    # ⑪g 死代码检查（提示性）：键本身已是 canonical 的条目**永不触发**（① 先返回）。
    dead = sorted(k for k in _TOPIC_ALIASES if k in canonical)
    check(
        "⑪g 别名表无恒等自映射死代码（键不应是 canonical）",
        not dead,
        f"死代码条目: {dead}" if dead else "无",
    )


def _c11_reverse() -> None:
    from memory.topics import canonical_names, normalize_topic

    canonical = canonical_names()
    # ⑪d 反向映射：canonical 名不得被 rag 同义词表改写成别的值
    #   反例来源：rag/synonyms.SYNONYM_MAP 含 '二叉排序树'→'二叉搜索树'，
    #   但 '二叉排序树' 本身是 canonical ⇒ 必须原样保留，不能被反向覆盖。
    reverse = ["二叉排序树", "平衡二叉树", "栈"]
    reverse_bad = [n for n in reverse if n in canonical and normalize_topic(n) != n]
    check(
        "⑪d 反向映射被拦住（canonical 不被同义词表改写）",
        not reverse_bad,
        "" if not reverse_bad else f"被改写: {reverse_bad}",
    )


def _c11_batch() -> None:
    from memory.topics import canonical_names, normalize_topics

    canonical = canonical_names()
    # ⑪e 写入路径：保序去重 + 结果全 canonical
    raw_in = ["TCP 流量控制", "页面置换算法", "Cache 映射方式", "平衡二叉树", "平衡二叉树"]
    out = normalize_topics(raw_in)
    check(
        "⑪e normalize_topics 保序去重且结果全 canonical",
        out == ["TCP 流量控制", "页面置换算法", "Cache 映射方式", "平衡二叉树"]
        and all(n in canonical for n in out),
        str(out),
    )


def _c10_config() -> None:

    from memory.remember import (
        batch_id_from_config,
        thread_id_from_config,
        user_id_from_config,
    )

    # ⑩a 显式优先
    c = {"configurable": {"user_id": "EXPLICIT", "thread_id": "T1", "question_batch_id": "B1"}}
    check(
        "⑩a 显式 config 优先（不破坏既有调用方）",
        user_id_from_config(c) == "EXPLICIT"
        and thread_id_from_config(c) == "T1"
        and batch_id_from_config(c) == "B1",
    )

    # ⑩c 无上下文不炸
    check(
        "⑩c 无 config 且无上下文 ⇒ 安全返回空（不抛错）",
        user_id_from_config(None) is None and thread_id_from_config(None) == "",
    )


async def _c10_runtime() -> None:

    # ⑩b 上下文回落
    from langchain_core.runnables import RunnableLambda

    from memory.remember import user_id_from_config

    async def _inner(_):
        return user_id_from_config(None)

    got = await RunnableLambda(_inner).ainvoke(
        None, config={"configurable": {"user_id": "CTX-UID"}}
    )
    check("⑩b 无显式 config ⇒ 回落运行时上下文取到 user_id", got == "CTX-UID", str(got))


async def _c10_episodes() -> None:

    # ⑩d 端到端：**经 config 解析取 uid** 写 episode ⇒ weak_topics 派生。
    #   ★ 关键：必须走 `user_id_from_config(None)`（而非显式传 uid），否则会绕过
    #     本缺陷所在的解析路径 —— 实测直接传 uid 时，护栏在破坏后**不变红**。
    from langchain_core.runnables import RunnableLambda

    from memory import initialize_store
    from memory.episodes import arecent_episodes
    from memory.namespaces import student_episodes_ns, student_profile_ns
    from memory.profile import aget_profile
    from memory.remember import record_grade, user_id_from_config
    from memory.runtime import set_store

    uid = "gate-ctx-e2e"
    async with initialize_store() as store:
        set_store(store)
        try:
            for ns in (student_episodes_ns(uid), student_profile_ns(uid)):
                for it in await store.asearch(ns, limit=200):
                    await store.adelete(ns, it.key)

            async def _write_two(_):
                # 模拟工具：只拿到 config 参数（此处为 None），uid 由回落解析得来
                resolved = user_id_from_config(None)
                if not resolved:
                    return None
                for _i in range(2):
                    await record_grade(
                        user_id=resolved,
                        topic="t",
                        score=40.0,
                        knowledge_points=["平衡二叉树"],
                    )
                return resolved

            resolved = await RunnableLambda(_write_two).ainvoke(
                None, config={"configurable": {"user_id": uid}}
            )
            eps = await arecent_episodes(store, uid)
            prof = await aget_profile(store, uid)
            check(
                "⑩d uid 经 config 解析（不是硬传）⇒ 真取到 user_id",
                resolved == uid,
                str(resolved),
            )
            check(
                "⑩d' 批改写入 ⇒ EPISODES 落库（不再静默跳过）",
                len(eps) == 2,
                f"{len(eps)} 条",
            )
            check(
                "⑩d'' 两次低分 ⇒ weak_topics 派生（跨会话召回的前置条件）",
                prof.weak_topics == ["平衡二叉树"],
                str(prof.weak_topics),
            )
        finally:
            for ns in (student_episodes_ns(uid), student_profile_ns(uid)):
                for it in await store.asearch(ns, limit=200):
                    await store.adelete(ns, it.key)
            set_store(None)


async def _c10_isolation() -> None:
    from langchain_core.runnables import RunnableLambda

    from memory.remember import user_id_from_config

    # ⑩e ★ 回落**不会**串号：`get_config()` 读的是 contextvar，asyncio 每个 Task
    #   持有自己的 context 副本 ⇒ 「参数为 None 时用运行时上下文」取到的是
    #   **本次 graph 调用**的 config，不是「并发里算到谁头上算谁的」。
    #   这条判据是为了把 B3 里**被推翻的那半**固化下来：推翻一次不够，要留证据。
    async def _whoami(_):
        first = user_id_from_config(None)
        await asyncio.sleep(0.02)  # 强制让 4 个任务交错
        return first, user_id_from_config(None)

    results = await asyncio.gather(
        *[
            RunnableLambda(_whoami).ainvoke(None, config={"configurable": {"user_id": f"U{i}"}})
            for i in range(4)
        ]
    )
    check(
        "⑩e 并发交错下，回落仍各取自己的 user_id（contextvar 隔离）",
        all(a == f"U{i}" and b == f"U{i}" for i, (a, b) in enumerate(results)),
        str(results),
    )


def _c10_contract() -> None:
    from memory.remember import thread_id_from_config, user_id_from_config

    # ⑩f 契约：显式 config **整块替换**、不做键级合并（当前无调用方踩到，故**不改行为**，
    #   只把语义钉住 —— 将来若要改成合并，必须让这条变红后由人裁决）。
    partial = {"configurable": {"thread_id": "T-PARTIAL"}}
    check(
        "⑩f 只写 thread_id 的显式 config ⇒ user_id 为 None（不回落补键，契约见 docstring）",
        user_id_from_config(partial) is None and thread_id_from_config(partial) == "T-PARTIAL",
    )
