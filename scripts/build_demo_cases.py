"""生成 Phase 0 demo 集（evals/datasets/demo/*.jsonl）—— **确定性、可复现**。

为什么用脚本而不是手敲 60+ 条
------------------------------
gold 里有一半是可从仓库现有资产**机械预填**的（§决策 #5：脚本预填 → 人工审核 → 冻结）：
- QA/Generate 的 `expected_kp` ← `evals/datasets/golden/sample_408.jsonl` 的 `metadata.knowledge_points`
- Verify 的 `expected_question_ids` ← `knowledge/exams/*/items.md` 的 `question_id` + `kp_ids`
- Grade 的 `question_stem` ← 同上；`answer_key` 可作标准答案
手敲会引入不可复现的漂移；脚本重跑即一致。

**不预填**（必须人工，标 `needs_review`）：
- Grade 的 `human_score`（0–100，须先立 scoring rubric 再标）
- Generate 的 `expected_difficulty` / `gold_answer`
- QA 的 `gold_points`

用法::

    PYTHONPATH=src uv run python scripts/build_demo_cases.py
    PYTHONPATH=src uv run python scripts/build_demo_cases.py --out-dir evals/datasets/demo
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ★ 资产解析统一走 task_eval.assets（**单一真源**）——
#   Gold Sanity Check 必须看到与生成器**同一份**解析结果，否则工具间口径会分裂。
from evaluation.task_eval.assets import (  # noqa: E402
    build_name2id,
    load_golden,
    load_kp_index,
    parse_exam_items,
)

DEFAULT_OUT = ROOT / "evals" / "datasets" / "demo"

# 每类 15 条（诊断基线）；Memory 6 条（两轮）
N_MAIN = 15
N_MEMORY = 6


# ── 读取现有资产（实现见 task_eval.assets）─────────────────


def map_kp_names(names: list[str], name2id: dict[str, str]) -> list[str]:
    """把考点名映射为 ID；映射不到的**原样保留**（并在 needs_review 里提示）。

    ★ 为什么必须映射：黄金集的 `metadata.knowledge_points` 是**中文名**（`存储系统`），
      而入库 chunk 的 `knowledge_points` 是**考点 ID**（`co.storage.cache`）。
      不统一命名空间，`kp_hit` 会恒为 0 —— 那是口径错配，不是检索失败（实测确认）。
    """
    return [name2id.get(n, n) for n in names]


# `parse_exam_items` / `load_golden` 已移至 `evaluation.task_eval.assets`（见文件头 import）


# ── 分层取数 ──────────────────────────────────────────────


def _round_robin_by(groups: dict[str, list[Any]], n: int) -> list[Any]:
    """按 key 轮转取数，保证跨学科均衡（不出现「前 15 条全是 ds」）。"""
    keys = sorted(groups)
    picked: list[Any] = []
    idx = 0
    while len(picked) < n and any(groups[k] for k in keys):
        k = keys[idx % len(keys)]
        if groups[k]:
            picked.append(groups[k].pop(0))
        idx += 1
    return picked[:n]


def _kp_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.replace("，", ",").split(",") if p.strip()]
    return []


# ── 各类 case ─────────────────────────────────────────────


def build_qa_cases(golden: list[dict[str, Any]], name2id: dict[str, str]) -> list[dict[str, Any]]:
    """QA：从黄金集「概念型」查询取，gold.expected_kp 自动预填（**已统一到考点 ID**）。"""
    pool = [g for g in golden if (g.get("metadata") or {}).get("query_type") in (None, "concept")]
    groups: dict[str, list[Any]] = defaultdict(list)
    for g in pool:
        groups[str((g.get("metadata") or {}).get("subject") or "?")].append(g)
    picked = _round_robin_by(groups, N_MAIN)
    cases = []
    for i, g in enumerate(picked, 1):
        meta = g.get("metadata") or {}
        cases.append(
            {
                "case_id": f"qa-{i:03d}",
                "task": "qa",
                "task_mode": "learn",
                "query": g["query"],
                "subject": meta.get("subject", ""),
                "gold": {
                    "expected_kp": map_kp_names(_kp_list(meta.get("knowledge_points")), name2id),
                    "reference": g.get("reference", ""),
                },
                "gold_status": "draft",
                "needs_review": ["gold.gold_points"],
                "notes": "gold_points 需人工从 reference 提炼；expected_kp 已由名字映射为考点 ID",
            }
        )
    return cases


def build_generate_cases(
    golden: list[dict[str, Any]], name2id: dict[str, str]
) -> list[dict[str, Any]]:
    """Generate：从黄金集「出题型」查询取，expected_kp 自动预填（已统一到考点 ID）。"""
    pool = [g for g in golden if (g.get("metadata") or {}).get("query_type") == "generate"]
    groups: dict[str, list[Any]] = defaultdict(list)
    for g in pool:
        groups[str((g.get("metadata") or {}).get("subject") or "?")].append(g)
    picked = _round_robin_by(groups, N_MAIN)
    cases = []
    for i, g in enumerate(picked, 1):
        meta = g.get("metadata") or {}
        cases.append(
            {
                "case_id": f"gen-{i:03d}",
                "task": "generate",
                "task_mode": "practice",
                "query": g["query"],
                "subject": meta.get("subject", ""),
                "gold": {
                    "expected_kp": map_kp_names(_kp_list(meta.get("knowledge_points")), name2id),
                    "expected_difficulty": None,
                    "gold_answer": None,
                },
                "gold_status": "draft",
                "needs_review": ["gold.expected_difficulty", "gold.gold_answer"],
                "notes": "难度（1–5 档）与 gold 答案需人工标注；expected_kp 已映射为考点 ID",
            }
        )
    return cases


def build_verify_cases(
    items: list[dict[str, Any]], kp_index: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    """Verify：按考点聚合真题题号，query 用考点中文名（多题 gold 才有判别力）。"""
    by_kp: dict[str, list[str]] = defaultdict(list)
    for it in items:
        for kp in it["kp_ids"]:
            by_kp[kp].append(it["question_id"])
    # 只取出现 ≥2 题的考点（单题 gold 无法体现 recall 的分数性）
    candidates = [(kp, sorted(set(ids))) for kp, ids in by_kp.items() if len(set(ids)) >= 2]
    groups: dict[str, list[Any]] = defaultdict(list)
    for kp, ids in candidates:
        subject = kp_index.get(kp, {}).get("subject") or kp.split(".")[0]
        groups[subject].append((kp, ids))
    picked = _round_robin_by(groups, N_MAIN)
    cases = []
    for i, (kp, ids) in enumerate(picked, 1):
        info = kp_index.get(kp, {})
        cases.append(
            {
                "case_id": f"ver-{i:03d}",
                "task": "verify",
                "task_mode": "verify",
                "query": f"{info.get('name', kp)}考过哪些真题？",
                "subject": info.get("subject", ""),
                "gold": {"expected_question_ids": ids},
                "gold_status": "draft",
                "needs_review": [],
                "notes": f"kp_id={kp}；expected_question_ids 由 kp_ids 反查（多题 gold）",
            }
        )
    return cases


def build_grade_cases(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grade：取选择题，题干**与选项**一起给，且**学生作答要覆盖答对/答错 × A/B/C/D**。

    ★ 2026-10-06 修（第二轮）：初版 `wrong = 排序后第一个非答案项` ⇒ **15/15 全是 `A`**，
      样本极度单一（无「答对」样本、无 B/C/D 样本）⇒ Grade 的 gold 分布严重偏斜，
      且 `score_tolerance@±10` 无从计算。
      现改为**答对/答错交替 + 错项轮换**，并让 `human_score` **客观可推**：

          选择题的「人工评分」本质是客观的 —— 对 = 100，错 = 0。
          故这里机械预填 `human_score`，并标 `draft` 供人工抽查。
          ⇒ `score_tolerance@±10` 由此**立即可算**，不必等人工逐条标。

    ⚠️ 局限：只覆盖选择题。填空/简答类需主观评分，本批不含（留待后续）。
    """
    # ★ 2026-10-06 修（第三轮）：**必须只收「answer_key 确实是 A/B/C/D」的题**。
    #   初版条件 `it["answer_key"]` 对字符串 `'null'` 也为真 ⇒ 无答案的题混进来，
    #   生成器又回退到 `opts[0]`（恒为 A）⇒ **凭空编造正确答案**，整批 gold 失真。
    #   这同时也是「student_answer 全是 A」的真正根因。
    _VALID_KEYS = {"A", "B", "C", "D"}
    pool = [
        it
        for it in items
        if it["question_type"] == "choice"
        and it["answer_key"] in _VALID_KEYS
        and it["stem"]
        and len(it["options"]) >= 2
    ]
    if not pool:
        return []
    groups: dict[str, list[Any]] = defaultdict(list)
    for it in pool:
        groups[it["subject"] or "?"].append(it)
    picked = _round_robin_by(groups, N_MAIN)
    cases = []
    for i, it in enumerate(picked, 1):
        opts = sorted(it["options"])
        correct = it["answer_key"] if it["answer_key"] in opts else (opts[0] if opts else "A")
        if i % 2 == 1:
            student = correct  # 奇数位：答对
        else:
            # 偶数位：答错。按**位置**均匀轮换（A→B→C→D→A…），
            # 保证四个选项都被覆盖 —— 初版只轮换「错项」列表，导致 D 只出现 1 次。
            k = (i // 2) % len(opts)
            student = opts[k] if opts[k] != correct else opts[(k + 1) % len(opts)]
        # 选择题的客观 gold：对 = 100，错 = 0
        human_score = 100.0 if student == correct else 0.0
        opt_lines = "\n".join(f"{k}. {v}" for k, v in sorted(it["options"].items()))
        stem_block = f"{it['stem']}\n{opt_lines}" if opt_lines else it["stem"]
        cases.append(
            {
                "case_id": f"grd-{i:03d}",
                "task": "grade",
                "task_mode": "grade",
                "query": f"请批改我的作答：\n{stem_block}\n我选 {student}。",
                "subject": it["subject"],
                "gold": {
                    "question_stem": stem_block,
                    "student_answer": student,
                    "human_score": human_score,
                    # ★ 必须 100：批改 agent 输出 0–100（schema/grading.py），
                    #   与真题卷面的 2 分制**不是一个量纲**，混用会让 ±10 容差失去意义。
                    "full_marks": 100.0,
                },
                "gold_status": "draft",
                "needs_review": ["gold.human_score（机械预填：选择题客观可推，请抽查）"],
                "notes": (
                    f"{it['question_id']}（卷面 {it['score']} 分）；answer_key={it['answer_key']}"
                    f"；student_answer={student}（{'答对' if student == correct else '答错'}）"
                ),
            }
        )
    return cases


# Memory：**跨会话**场景，手工编写（自动化无法产出有意义的记忆场景）
#
# ★ 2026-10-06 Phase 1.5 Step 4 重写（原 6 条作废）。
#
# 为什么原 6 条必须重写
# --------------------
# 原实现全是「**单 thread 两轮**」（`turns` 两句话，跑在同一个 thread 里），
# 而期望的记忆是「身份 / 进度 / 学习偏好」—— 这些**产品根本不写入 Store**：
#
#   - `abuild_memory_card` 只读 `weak_topics`（`memory/working.py`）；
#   - `weak_topics` 只能由 **grade episodes** 派生（`memory/weak_topics.py`）；
#   - 「从对话抽取画像」的写入路径**不存在**（`src/memory/` 零命中）。
#
# ⇒ 旧 6 条按新旧口径都必然得 0，且「第 2 轮记得第 1 轮的话」完全可由 checkpointer
#   解释，**证明不了 Store 起了作用**。这是 case 与产品能力错配，不是产品退化。
#
# 新设计：两段**独立会话**（`sessions` 字段，见 runner 的 memory 分支）
# ------------------------------------------------------------------
#   Session A（thread-A）：提交错题作答 → grading_agent 批改 → record_grade 写 episode
#                           （正样本/阈值样本在同一段内**多次**批改，以累计 weak 计数）
#   Session B（thread-B）：**新会话**（新 thread）问复习建议 → 应召回 Store 里的 weak_topics
#
# 唯一能连通两段的是 **Store**（thread 不同、user_id 相同）⇒ 召回必来自长期记忆，
#   checkpointer 在此结构下**无法**解释召回（两段是不同 thread，没有共享历史）。
#
# ★ 为什么每段可以只有 1–2 轮：跨会话语义下「多轮」不是重点 —— 重点在**段间**
#   是否只靠 Store 连通。故 sanity 的「≥2 轮」按**全会话合计**算（见 gold_sanity）。
#
# 字段契约（与 `cases.py` / `memory_scorer.py` 一一对应）
# -----------------------------------------------------
#   expected_memory.type            ∈ {"weak_topics"}
#   expected_memory.values          ★ 必须 kp_index 的 **canonical name**
#   expected_memory.should_be_recalled  True=正样本 / False=负样本
#   expected_answer_property.forbidden_values  必填，可为 []
#
# 阈值事实（`core/settings.py`，决定 case 怎么构造）
# -------------------------------------------------
#   MEMORY_WEAK_SCORE   60 → score < 60 记 weak
#   MEMORY_GOOD_SCORE   85 → score >= 85 记 good
#   MEMORY_WEAK_MIN_HITS 2 → 同 KP 累计 weak >= 2 才进 weak_topics
#   MEMORY_WEAK_CLEAR_MIN_GOOD_HITS 2 → good >= 2 且 weak < 2 ⇒ 移出
#
# ★ 6 条怎么覆盖阈值（每条只变一个变量，其余固定）
# -------------------------------------------------
#   mem-001/002/003  正样本：同 KP 低分 2 次 ⇒ weak=2 ≥ MIN_HITS ⇒ 应召回
#   mem-004          负样本：同 KP 低分 **1** 次 ⇒ weak=1 < MIN_HITS ⇒ 不召回（验 MIN_HITS）
#   mem-005          负样本：全新用户无批改 ⇒ 无 episode ⇒ 卡空（验 recalled 非恒真）
#   mem-006          负样本：同 KP **高分** 2 次 ⇒ 记 good 不记 weak（验 WEAK_SCORE）
#
# ★★ setup_conditions（case-validity 契约，2026-10-06 Step 5 用户裁决）
# ------------------------------------------------------------------
#   为什么必须声明：case 的**前置条件**（「两次低分」「两次高分」）不能**假定**
#   grading LLM 一定给出预期分数 —— 分数有随机性。若 mem-006 假定两次高分、
#   实际跑出 100/52，那是 **A 段没凑成条件**（case_invalid），**不是**产品失败。
#   故：
#     - 正样本/阈值样本（要求低分）→ grade_score_bands=[(0,59),(0,59)]（< WEAK_SCORE=60）
#     - mem-006（要求高分）        → grade_score_bands=[(60,100),(60,100)]（≥ WEAK_SCORE）
#     - mem-004（1 次低分）         → min_grade_calls=1, bands=[(0,59)]
#     - mem-005（不发生批改）       → min_grade_calls=0（显式声明「无批改」）
#   区间用 WEAK_SCORE(60) 作分界：<60 记 weak、>=60 不记 weak，与产品阈值同源。
#   ★ 上界用 60 还是 100 的区别：低分档 `(0,59)` 表示「必须真低分才算弱」；
#     但**正样本的关键是 weak 计数**，若某次恰打 62 分（不记 weak）⇒ 计数不足 ⇒
#     该 case 的前置条件其实没成立，应判 invalid。故上界严取 59。
#
# ★ canonical name 对照（实测，非猜测）：
#     「平衡二叉树」= ds.tree.avl.name（**不是** AVL树）
#     「图」        = ds.graph.name   （**不是** 图论）
#     「排序」      = ds.sort.name
#     「TCP 流量控制」（**含空格**）
_MEMORY_SPECS: list[dict[str, Any]] = [
    # ── 正样本：Session A 反复批改同一 KP（≥2 hits、分数低）⇒ 应召回 ─────
    #    每段会话末尾有一句「新会话」的追问（Session B），用于测**跨 thread 召回**。
    {
        "sessions": [
            [
                "帮我批改这道题：在右图所示的平衡二叉树中，插入关键字 48 后得到一棵新平衡二叉树。"
                "在新平衡二叉树中，关键字 37 所在结点的左、右子结点保存的关键字号分别是？我的答案：20 和 53",
                "再批改一题：在平衡二叉树中删除一个结点后又插入同一结点，若原树高为 5，"
                "则新树的高可能是多少？我答 4。",
            ],
            [
                "新的一天，我想听点复习建议：我最近哪些知识点比较薄弱？",
            ],
        ],
        "expected_memory": {
            "type": "weak_topics",
            "values": ["平衡二叉树"],
            "should_be_recalled": True,
        },
        "expected_answer_property": {"forbidden_values": ["栈", "队列"]},
        "setup_conditions": {"min_grade_calls": 2, "grade_score_bands": [[0, 59], [0, 59]]},
        "subject": "ds",
        "note": "正样本·A 段 2 次低分批改（平衡二叉树）⇒ weak≥2 ⇒ B 段新会话应召回",
    },
    {
        "sessions": [
            [
                "帮我看看这道题对不对：下列关于无向连通图特性的叙述中，正确的是。"
                "I. 所有顶点的度之和为偶数 II. 边数大于顶点个数减 1 III. 至少有一个顶点的度为 1。我选 III。",
                "再做一道图题：用邻接矩阵存储一个有 6 个顶点 10 条边的无向图，"
                "该矩阵中 1 的个数是多少？我答 10。",
            ],
            [
                "换了个会话，帮我复盘一下：根据我的做题记录，我在哪块需要加强？",
            ],
        ],
        "expected_memory": {
            "type": "weak_topics",
            "values": ["图"],
            "should_be_recalled": True,
        },
        "expected_answer_property": {"forbidden_values": ["排序", "栈"]},
        "setup_conditions": {"min_grade_calls": 2, "grade_score_bands": [[0, 59], [0, 59]]},
        "subject": "ds",
        "note": "正样本·A 段 2 次低分批改（图）⇒ weak≥2 ⇒ B 段新会话应召回",
    },
    {
        "sessions": [
            [
                "批改一下：对于下列关键字序列 5, 8, 12, 19, 28, 20, 15, 22，"
                "请判断它是否构成小根堆。我认为构成。",
                "再批改一道：对序列 49, 38, 65, 97, 76 进行一趟快速排序，"
                "以 49 为枢轴，得到的结果是什么？我写成 38, 49, 65, 97, 76。",
            ],
            [
                "我开个新会话问你：结合我之前的作答，给我一份针对性的补强清单。",
            ],
        ],
        "expected_memory": {
            "type": "weak_topics",
            "values": ["排序"],
            "should_be_recalled": True,
        },
        "expected_answer_property": {"forbidden_values": ["图", "栈"]},
        "setup_conditions": {"min_grade_calls": 2, "grade_score_bands": [[0, 59], [0, 59]]},
        "subject": "ds",
        "note": "正样本·A 段 2 次低分批改（排序/堆）⇒ weak≥2 ⇒ B 段新会话应召回",
    },
    # ── 负样本 1：同一 KP 只批改 **1** 次（< MIN_HITS=2）⇒ 不应入 weak_topics ──
    {
        "sessions": [
            [
                "帮我批改：若平衡二叉树的高度为 6，且所有非叶结点的平衡因子均为 1，"
                "则该平衡二叉树的结点总数为多少？我答 20。",
            ],
            [
                "换个会话，看看我有没有需要复习的薄弱点？",
            ],
        ],
        "expected_memory": {
            "type": "weak_topics",
            "values": ["平衡二叉树"],
            "should_be_recalled": False,  # ★ 1 hit < MIN_HITS(2) ⇒ 不该召回
        },
        "expected_answer_property": {"forbidden_values": []},
        "setup_conditions": {"min_grade_calls": 1, "grade_score_bands": [[0, 59]]},
        "subject": "ds",
        "note": "负样本·同一 KP 仅 1 hit 未达阈值⇒**不该**召回（验证 MIN_HITS 真在起作用）",
    },
    # ── 负样本 2：全新用户，A 段完全不批改 ⇒ Store 里没有 weak_topics ──
    {
        "sessions": [
            ["你好，我想了解一下考研 408 的备考节奏。"],
            ["再问一句，408 四门课大概各占多少分？"],
        ],
        "expected_memory": {
            "type": "weak_topics",
            "values": ["图"],
            "should_be_recalled": False,  # ★ 无任何 grade episode ⇒ 卡必空
        },
        "expected_answer_property": {"forbidden_values": []},
        # ★ 显式声明「A 段不应发生批改」（min=0 也是有效约束：多批了反而不符设计）
        "setup_conditions": {"min_grade_calls": 0},
        "subject": "ds",
        "note": "负样本·全新用户无写入⇒卡必空（验证 recalled 非恒真、非恒假）",
    },
    # ── 负样本 3：批改且答对（≥ GOOD_SCORE）⇒ 记 good 而非 weak ⇒ 不召回 ──
    {
        "sessions": [
            [
                "帮我批改这道题，我很有把握：下列关于图的叙述中，正确的是。"
                "I. 回路是简单路径 II. 存储稀疏图用邻接矩阵比邻接表更省空间 "
                "III. 若有向图存在拓扑序列，则其邻接矩阵一定是三角矩阵。"
                "这道题的正确选项我核对过是 III。",
                "再来一道我也确定：含 n 个顶点的无向连通图最少有多少条边？答 n-1。",
            ],
            [
                "新会话：我在图这部分还有需要重点复习的地方吗？",
            ],
        ],
        "expected_memory": {
            "type": "weak_topics",
            "values": ["图"],
            "should_be_recalled": False,  # ★ 期望答对 ⇒ score 高 ⇒ 不计 weak
        },
        "expected_answer_property": {"forbidden_values": []},
        # ★ 高分档：两次都必须 ≥ WEAK_SCORE(60) —— 否则不构成「高分负样本」，属 case_invalid
        "setup_conditions": {"min_grade_calls": 2, "grade_score_bands": [[60, 100], [60, 100]]},
        "subject": "ds",
        "note": "负样本·同 KP 多次但均高分⇒记 good 不计 weak（验证 WEAK_SCORE 阈值真在起作用）",
    },
]


def build_memory_cases() -> list[dict[str, Any]]:
    """Memory case：**跨会话**（`sessions`）而非单 thread 多轮（`turns`）。

    ★ 与旧实现的差别：`sessions` 是「会话列表的列表」—— 每个内层列表是一段
      **独立对话**（独立 thread）。真正的执行走 `sessions`（`TaskCase.all_sessions`）；
      `turns` 仅为**向后兼容镜像**（各段会话首句），供仍读 `turns` 的旧代码路径使用。
    """
    cases = []
    for i, spec in enumerate(_MEMORY_SPECS[:N_MEMORY], 1):
        sessions = spec["sessions"]
        first = sessions[0] if sessions else [""]
        flat = [t for seg in sessions for t in seg]
        cases.append(
            {
                "case_id": f"mem-{i:03d}",
                "task": "memory",
                "task_mode": "learn",
                "query": first[0],
                # `turns` = **全部会话的轮次摊平**（= 真正会执行的轮次序列）。
                # 与 `sessions` 含义一致（sessions 是其**分组**视图），故二者不矛盾；
                # 保留 turns 是为兼容仍按「顺序轮次」读取的旧代码路径（如 judge 提示词拼接）。
                "turns": flat,
                # ★ `sessions` 是权威字段：驱动 run_sessions 的每段独立 thread
                "sessions": sessions,
                "subject": spec.get("subject", ""),
                "gold": {
                    "expected_memory": spec["expected_memory"],
                    "expected_answer_property": spec["expected_answer_property"],
                    # ★ case-validity：A 段前置条件（由实际运行结果验收，非假定）
                    "setup_conditions": spec.get("setup_conditions"),
                },
                "gold_status": "draft",
                "needs_review": [],
                "notes": spec["note"],
            }
        )
    return cases


# ── 写出 ──────────────────────────────────────────────────

_HEADERS = {
    "qa": [
        "# Phase 0 demo · QA（learn/method/explain）",
        "# schema 见 evals/datasets/demo/README.md；gold_status=draft 需人工审核",
    ],
    "generate": [
        "# Phase 0 demo · Generate（practice）",
        "# 五项 pass 判据见 docs/EFFECT_PLAN.md §3.1（v1.0 冻结）",
    ],
    "grade": [
        "# Phase 0 demo · Grade（grade，0–100 制）",
        "# score_tolerance@±10 已锁定；human_score 须先立 rubric 再标",
    ],
    "verify": [
        "# Phase 0 demo · Verify（verify）",
        "# Phase 0 用 exam_hit@5 作代理；question_id_recall@5 属 Phase 1",
    ],
    "memory": [
        "# Phase 0 demo · Memory（**跨会话**）",
        "# 每 case 两段**独立会话**（不同 thread、同一 user_id）：",
        "#   A 段批改错题→record_grade 写 episode→compute_weak_topics；",
        "#   B 段**新会话**问建议→应召回 Store 里的 weak_topics（thread 不同⇒只能来自 Store）。",
        "# 主指标（**全部机械判定**，judge 不参与）：recalled_pass / used / correct",
        "#   recalled_pass = (卡里有 values) == should_be_recalled（负样本对齐）",
        "#   used   = 回复含 expected_memory.values 中任一",
        "#   correct= used 且 回复不含 forbidden_values 中任一",
        "# ★ values 必须是 kp_index 的 canonical name（如「平衡二叉树」而非「AVL树」）",
    ],
}


def write_cases(out_dir: Path, name: str, cases: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}_cases.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for line in _HEADERS[name]:
            f.write(line + "\n")
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  {path.relative_to(ROOT)}  ({len(cases)} 条)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 Phase 0 demo 集")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    kp_index = load_kp_index()
    name2id = build_name2id(kp_index)
    items = parse_exam_items()
    golden = load_golden()
    print(f"资产：考点 {len(kp_index)} · 真题 {len(items)} · 黄金集 {len(golden)}")
    print(f"输出 → {out_dir}")

    write_cases(out_dir, "qa", build_qa_cases(golden, name2id))
    write_cases(out_dir, "generate", build_generate_cases(golden, name2id))
    write_cases(out_dir, "grade", build_grade_cases(items))
    write_cases(out_dir, "verify", build_verify_cases(items, kp_index))
    write_cases(out_dir, "memory", build_memory_cases())
    return 0


if __name__ == "__main__":
    sys.exit(main())
