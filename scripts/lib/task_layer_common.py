"""Task-mode × layer 实验的共享原语（`basic_rag_ablation` / `task_mode_layer_policy` 共用）。

★ 为什么抽出来：原先 `task_layer_ablation` 与 `task_mode_layer_policy` 各自**逐字复制**了
  同一套「任务标注黄金 query + 任务目标层 + 证据包分层/泄漏判读」——query 集一旦漂移，
  「跨实验可比」的承诺就**静默失效**（不报错，只是两次实验不再同源）。此处作为唯一真源。

★ `task_layer_common` 不做 `sys.path` 注入：调用方（脚本入口）已先把 `src` 放上路径，
  本模块在 import 时其自身的 `rag.*` / `schema.*` 依赖即可解析。
"""

from __future__ import annotations

import re
from typing import Any

from rag.retrieval.evidence_policy import (
    apply_evidence_policy,
    finalize_with_layer_ranking,
)
from rag.retrieval.retriever import aretrieve_evidence_with_retry
from rag.retrieval.task_policy import policy_for_mode
from schema.task_policy import TaskPolicy

# 任务标注的黄金 query（每模式多条，覆盖四科）
TASK_QUERIES: dict[str, list[str]] = {
    "learn": [
        "什么是二叉排序树？",
        "什么是死锁？",
        "进程和线程的区别是什么？",
        "Cache 的映射方式有哪些？",
        "TCP 三次握手的过程是什么？",
        "什么是虚拟存储器？",
    ],
    "method": [
        "BST 删除时双支结点怎么处理？",
        "如何用银行家算法避免死锁？",
        "页面置换算法 LRU 怎么实现？",
        "Dijkstra 算法的步骤是什么？",
        "如何判断一个二叉树是平衡二叉树？",
        "TCP 拥塞控制怎么实现？",
    ],
    "practice": [
        "给我一道死锁练习题",
        "来一道 BST 删除的练习题",
        "出一道进程同步的题目",
        "给一道 Cache 映射的练习",
    ],
    "grade": [
        "请批改我对「进程死锁四个必要条件」的回答：互斥、占有并等待、不可剥夺、循环等待",
        "批改我的答案：TCP 三次握手是 SYN、SYN+ACK、ACK",
        "我对「页面置换 OPT 是最优算法」的理解是：它永不缺页。请批改",
    ],
    "explain": [
        "2019-Q2 为什么树的后根遍历对应二叉树的中序？",
        "2019-Q11 为什么选 B？请详细解析",
        "2020-Q2 这道题的解题思路是什么？",
    ],
    "verify": [
        "BST 删除考过哪些真题？",
        "死锁在历年真题中出现过吗？",
        "Cache 映射方式考过几次？",
    ],
}

# 任务专有指标：期望命中的语义层
TASK_TARGET_LAYER: dict[str, tuple[str, ...]] = {
    "learn": ("basic",),
    "method": ("advanced",),
    "practice": ("advanced", "exams"),
    "grade": ("exams",),
    "explain": ("exams",),
    "verify": ("exams",),
}

_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer|correct_answer", re.I)
_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】|正确答案|标准答案")


def _pack_layers(fused) -> list[str]:
    out = []
    for ev in fused.text_evidences or []:
        v = str((ev.metadata or {}).get("kb_depth") or "")
        out.append(v if v in ("basic", "advanced", "exams") else "legacy")
    return out


def _pack_blob(fused) -> str:
    parts = []
    for ev in fused.text_evidences or []:
        parts.append(ev.content or "")
        parts.append(str(ev.metadata or ""))
    return "\n".join(parts)


def _ours_policy(mode: str) -> TaskPolicy:
    return policy_for_mode(mode)  # type: ignore[arg-type]


def _baseline_policy(mode: str) -> TaskPolicy:
    """baseline：所有任务平铺 L1/L2/L3，legacy 等同主池。"""
    p = policy_for_mode(mode)  # type: ignore[arg-type]
    # 用 model_copy 覆盖层偏好与 legacy 策略（安全字段不动）
    return p.model_copy(
        update={
            "preferred_layers": ["basic", "advanced", "exams"],
            "legacy_policy": "include",
        }
    )


async def run_one(query: str, mode: str, policy: TaskPolicy) -> dict[str, Any]:
    fused, _ = await aretrieve_evidence_with_retry(
        query=query,
        k=5,
        use_rerank=True,
        max_retries=0,
        use_llm_verify=False,
        filter=policy.eligibility_where(),
        preferred_layers=list(policy.preferred_layers),
        eligible_layers=policy.eligible_semantic_layers(),
    )
    fused = finalize_with_layer_ranking(fused, policy, keep=5)
    fused, flags = apply_evidence_policy(fused, policy)

    layers = _pack_layers(fused)
    targets = TASK_TARGET_LAYER.get(mode, ())
    layer_hit = any(t in layers for t in targets)
    blob = _pack_blob(fused)
    # 泄漏只在「答案隐藏」的模式上有意义（learn/method/practice/verify）
    # grade/explain 的 answer_policy=released，含答案是预期
    answer_hidden = mode in ("learn", "method", "practice", "verify")
    leakage = bool(answer_hidden and (_ANS_FIELD_RE.search(blob) or _ANS_BODY_RE.search(blob)))
    return {
        "query": query,
        "mode": mode,
        "layers": layers,
        "layer_hit": layer_hit,
        "leakage": leakage,
        "answer_hidden_mode": answer_hidden,
        "n_pack": len(layers),
        "legacy_policy": policy.legacy_policy,
    }
