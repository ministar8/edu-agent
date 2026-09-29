"""Evidence Policy：release 唯一出口（设计定稿 §5）。

职责：
- 按 RetrievalPolicy 裁 FusedEvidence（exam_answer / 答案字段 / 题号）
- 置 release flags，供 Agent 约束

禁止：
- 在 BM25/RRF/Reranker 内做权限判断
- 从索引删除答案（只裁 Pack）
"""

from __future__ import annotations

import re
from typing import Any

from rag.evidence import FusedEvidence, TextEvidence
from schema.retrieval_policy import RetrievalPolicy

_ANSWER_KEY_RE = re.compile(r"\banswer_key\b|\breference_answer\b", re.I)
_QUESTION_ID_RE = re.compile(r"\b(?:19|20)\d{2}-Q\d+\b")
_ANSWER_BODY_RE = re.compile(
    r"(^|\n)\s*(答案[:：]|【答案】|正确答案|标准答案|解析[:：]?)[^\n]*"
    r"|(^|\n)\s*-\s*\*+\s*[A-D][.、．][^*]*\*+\s*✅[^\n]*"
    r"|\*+\s*[A-D][.、．][^*]{0,40}\*+\s*✅"
    r"|✅",
    re.I,
)


def _meta(ev: TextEvidence) -> dict[str, Any]:
    return dict(ev.metadata or {})


def _doc_role(ev: TextEvidence) -> str:
    return str(_meta(ev).get("doc_role") or "")


def _is_exam_answer(ev: TextEvidence) -> bool:
    return _doc_role(ev) == "exam_answer"


def _is_exam_item(ev: TextEvidence) -> bool:
    return _doc_role(ev) == "exam_item"


def _is_exam_paper(ev: TextEvidence) -> bool:
    return _doc_role(ev) == "exam_paper"


def _resource_blocked(policy: RetrievalPolicy, ev: TextEvidence) -> bool:
    """exam_resources eligibility（与召回侧 where 双保险）。"""
    if _is_exam_answer(ev) and policy.eligibility_block_exam_answer:
        return True
    if _is_exam_item(ev) and policy.eligibility_block_exam_item:
        return True
    if _is_exam_paper(ev) and policy.eligibility_block_exam_paper:
        return True
    return False


def _is_incomplete_stem(ev: TextEvidence) -> bool:
    m = _meta(ev)
    gf = m.get("gap_fields") or ""
    if isinstance(gf, str):
        return "stem" in gf and "missing" in str(m.get("gap_status") or "")
    return False


def _strip_answer_fields(meta: dict[str, Any]) -> dict[str, Any]:
    """剥离答案类 metadata（含旧题库 qa.* 字段）。"""
    out = dict(meta)
    for k in list(out.keys()):
        lk = str(k).lower()
        if (
            lk in {"answer_key", "reference_answer", "answer", "correct_answer"}
            or "answer" in lk
            or lk.startswith("qa.")
        ):
            out.pop(k, None)
    return out


def _body_has_answer(text: str) -> bool:
    return bool(_ANSWER_BODY_RE.search(text or ""))


# 语义知识层（L1/L2/L3）。legacy 是**资产质量/迁移状态**，不在其中。
_SEMANTIC_LAYERS = ("basic", "advanced", "exams")


def semantic_layer(ev: TextEvidence) -> str:
    """返回 L1/L2/L3 语义层名；无 kb_depth（legacy 资产）返回空串。

    ★ 不要把空串/legacy 当第四层 —— 那是资产状态，用 `is_legacy_asset`。
    """
    v = str((ev.metadata or {}).get("kb_depth") or "")
    return v if v in _SEMANTIC_LAYERS else ""


def is_legacy_asset(ev: TextEvidence) -> bool:
    """资产质量：无有效 kb_depth = 迁移未完成的 legacy 资产。"""
    return semantic_layer(ev) == ""


def apply_layer_ranking(
    fused: FusedEvidence,
    policy: RetrievalPolicy,
    *,
    boost: float = 1.25,
) -> FusedEvidence:
    """ranking：preferred_layers 软加权（不改安全字段；系数可调）。

    只做语义层偏好排序；**legacy 入池策略**（exclude/fallback/include）
    在 `finalize_with_layer_ranking`，不在这里。
    """
    preferred = list(policy.preferred_layers)

    def _key(item: tuple[int, TextEvidence]) -> tuple[float, float, int]:
        idx, ev = item
        layer = semantic_layer(ev)
        score = float((ev.metadata or {}).get("score") or ev.score or 0.0)
        w = boost if layer in preferred else 1.0
        return (-score * w, -w, idx)

    ranked = [ev for _, ev in sorted(enumerate(fused.text_evidences or []), key=_key)]
    out = fused.model_copy(deep=True)
    out.text_evidences = ranked
    return out


def finalize_with_layer_ranking(
    fused: FusedEvidence,
    policy: RetrievalPolicy,
    *,
    keep: int = 5,
    boost: float = 1.35,
) -> FusedEvidence:
    """ranking + 截断 + **legacy 池策略**。

    主检索池 = L1/L2/L3（semantic_layer 非空）；legacy 是 fallback 池：

    - `exclude`  ：legacy 不进证据包；不足 keep 显式降级，不回填
    - `fallback` ：先主池，不足 keep 才按 score 补入 legacy；仍不足才降级
    - `include`  ：legacy 与主池同等入池（仅调试/特殊场景）

    必须在**扩大候选**之后调用，否则 preferred 层进不了池就无法提权。
    """
    pool_policy = policy.legacy_pool_policy
    items = list(fused.text_evidences or [])
    main_items = [ev for ev in items if not is_legacy_asset(ev)]
    legacy_items = [ev for ev in items if is_legacy_asset(ev)]
    dropped_legacy = 0
    if pool_policy == "exclude":
        dropped_legacy = len(legacy_items)
        legacy_items = []
    elif pool_policy == "include":
        # 与主池混排，后续统一 ranking
        main_items = items
        legacy_items = []

    def _score(ev: TextEvidence) -> float:
        return float((ev.metadata or {}).get("score") or ev.score or 0.0)

    filtered = fused.model_copy(deep=True)
    filtered.text_evidences = main_items
    ranked = apply_layer_ranking(filtered, policy, boost=boost)
    pack = list(ranked.text_evidences or [])
    if keep > 0 and len(pack) > keep:
        pack = pack[:keep]

    used_fallback = 0
    if pool_policy == "fallback" and keep > 0 and len(pack) < keep and legacy_items:
        # 主池不足：按 score 从 fallback 池补入（显式记录，不静默）
        reserve = sorted(legacy_items, key=_score, reverse=True)
        need = keep - len(pack)
        filled = reserve[:need]
        pack.extend(filled)
        used_fallback = len(filled)

    out = fused.model_copy(deep=True)
    out.text_evidences = pack
    # final_context 与 pack 对齐，避免策略裁剪后残留已剔除正文
    out.final_context = "\n\n".join((e.content or "") for e in pack)

    insufficient = keep > 0 and len(pack) < keep
    out.metadata = {
        **(out.metadata or {}),
        "layer_pack": {
            "legacy_pool_policy": pool_policy,
            "n_main": len(main_items),
            "n_legacy_reserve": len(legacy_items),
            "dropped_legacy": dropped_legacy,
            "used_fallback": used_fallback,
            "n_pack": len(pack),
            "keep": keep,
            "degraded": insufficient,
        },
    }
    return out


def apply_evidence_policy(
    fused: FusedEvidence,
    policy: RetrievalPolicy,
) -> tuple[FusedEvidence, dict[str, Any]]:
    """返回 (裁剪后的 FusedEvidence, release flags)。不改索引。"""
    kept: list[TextEvidence] = []
    hide_answer = not policy.answer_released
    hide_exp = policy.explanation_policy == "hidden"
    verified_only = policy.explanation_policy == "verified_only"

    for ev in fused.text_evidences:
        # --- eligibility 类（安全前置在召回；此处再兜底）---
        if _resource_blocked(policy, ev):
            continue
        if _is_incomplete_stem(ev):
            continue

        meta = _meta(ev)
        content = ev.content or ""

        # practice：禁止具体题号 / related_exams 泄漏（release；索引不动）
        if policy.eligibility_block_question_ids or not policy.allow_question_id_leak:
            if _QUESTION_ID_RE.search(content) or str(meta.get("question_id") or ""):
                # 题干 chunk 可保留正文，但剥题号字段与正文题号
                content = _QUESTION_ID_RE.sub("（题目）", content)
                meta.pop("related_exams", None)
                meta.pop("question_id", None)
            else:
                meta.pop("related_exams", None)
                meta.pop("question_id", None)

        # --- release：字段与正文 ---
        if hide_answer:
            meta = _strip_answer_fields(meta)
            # 旧题库 / 解析正文中的答案行一并抹掉
            if (
                _body_has_answer(content)
                or re.search(r"\*\*[A-D][.、．].*✅", content)
                or "✅" in content
            ):
                content = re.sub(
                    r"(^|\n)\s*(答案[:：]|【答案】|正确答案|标准答案|解析[:：]?)[^\n]*",
                    r"\1…",
                    content,
                )
                content = re.sub(r"\*+\s*([A-D][.、．][^*]{0,40})\*+\s*✅", r"\1", content)
                content = re.sub(r"✅", "", content)
                content = re.sub(r"\n{3,}", "\n\n", content)

        if hide_exp and _is_exam_answer(ev):
            continue

        if verified_only and str(meta.get("explanation_status") or "") != "verified":
            meta["explanation_unverified"] = str(meta.get("explanation_status") or "") in (
                "scan",
                "ocr",
                "none",
            )

        new_ev = ev.model_copy(deep=True)
        new_ev.metadata = meta
        new_ev.content = content
        kept.append(new_ev)

    layer_pack = (fused.metadata or {}).get("layer_pack") or {}
    flags = {
        "task_mode": policy.task_mode,
        "answer_released": policy.answer_released,
        "explanation_released": policy.explanation_released,
        "layer_policy_id": policy.layer_policy_id,
        # legacy 池策略结果（fallback 补入 / exclude 剔除后的包体状态）
        "legacy_pool_policy": policy.legacy_pool_policy,
        "layer_degraded": bool(layer_pack.get("degraded")),
        "dropped_legacy": int(layer_pack.get("dropped_legacy") or 0),
        "used_fallback": int(layer_pack.get("used_fallback") or 0),
    }

    rebuilt = fused.model_copy(deep=True)
    rebuilt.text_evidences = kept
    # final_context 由 kept 重建，避免原始融合正文带答案
    if kept:
        rebuilt.final_context = "\n\n".join((e.content or "") for e in kept)
    elif not policy.answer_released:
        rebuilt.final_context = ""
    if not policy.answer_released:
        ctx = rebuilt.final_context or ""
        ctx = re.sub(
            r"(^|\n)\s*(答案[:：]|【答案】|正确答案|标准答案|解析[:：]?)[^\n]*", r"\1…", ctx
        )
        ctx = re.sub(r"\*+\s*([A-D][.、．][^*]{0,40})\*+\s*✅", r"\1", ctx)
        ctx = re.sub(r"✅", "", ctx)
        rebuilt.final_context = ctx
    rebuilt.metadata = {**(rebuilt.metadata or {}), "evidence_policy": flags}
    return rebuilt, flags
