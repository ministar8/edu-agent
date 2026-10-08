"""主张状态推导（EVIDENCE_CHAIN.md §1.1）。状态是算出来的，不是写出来的。"""

from __future__ import annotations

CLAIM_PROVEN = "已证明"
CLAIM_MEASURED = "已测量未证明"
CLAIM_UNMEASURED = "未测量"


def derive_status(
    claim: dict,
    *,
    falsify_passed: bool,
    tier_ok: bool,
    discriminating: bool,
    provenance_match: bool,
    signed: bool,
) -> str:
    """★ 参数叫 `falsify_passed` 而不是 `falsified`：`falsified` 字面意思是「主张被证伪」，
    读 `if falsified: return CLAIM_PROVEN` 会把意思整个反过来。这里为真表示
    「mutation 取证成功：判据对它声明的每个契约输入都敏感」。"""
    if not discriminating and not falsify_passed:
        return CLAIM_UNMEASURED
    if not (falsify_passed and tier_ok and discriminating and provenance_match and signed):
        return CLAIM_MEASURED
    return CLAIM_PROVEN


def artifact_status(path: str, *, superseded_by: str = "", reason: str = "") -> dict:
    return {
        "path": path,
        "status": "superseded" if superseded_by else "active",
        "superseded_by": superseded_by,
        "reason": reason,
    }


def boundary_calibrated(human: list[float], *, threshold: float = 4.0, min_each: int = 3) -> bool:
    """judge 在**门槛边界两侧**都见过人工分，才算校准过。

    ★ 门槛一律是 `final_quality ≥ 4`，所以只有 5 分的校准集证明不了「3 分该判不过」。
      实测 `evals/datasets/demo/calibration_30.jsonl` 的 human 分布 = {5×28, 2×1, 0×1}
      ⇒ below=2 < 3 ⇒ False。这不是缺陷，是**尚未做过的事**，必须如实进状态词。
    """
    below = sum(1 for h in human if h < threshold)
    above = sum(1 for h in human if h >= threshold)
    return below >= min_each and above >= min_each


def repeat_jitter(by_run: list[dict[str, float]], *, case_ids: list[str]) -> dict[str, float]:
    """同 case 跨重复运行的 `final_quality` 极差。缺重复运行 ⇒ 返回 {}（= 未量化）。"""
    out: dict[str, float] = {}
    for cid in case_ids:
        vals = [r[cid] for r in by_run if cid in r]
        if len(vals) >= 2:
            out[cid] = max(vals) - min(vals)
    return out
