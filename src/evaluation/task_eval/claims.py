"""主张状态推导（EVIDENCE_CHAIN.md §1.1）。状态是算出来的，不是写出来的。"""

from __future__ import annotations

from typing import Any

CLAIM_PROVEN = "已证明"
CLAIM_MEASURED = "已测量未证明"
CLAIM_UNMEASURED = "未测量"

# tier 声明的是「这个数字由谁决定」，不是可随手改的样式（Task 6 评审 I-2 的根因就是这个数由人
# 手写、且没人检查它凭什么）。锚点必须是文档/裁定记录里查得到的**实名**，自由文本不算依据。
# ★ 这张白名单**只有一份**（Task 7 Step 4b 从 `scripts/build_claim_ledger.py` 上移）：
#   ledger 行侧与 registry 判据侧共用 ⇒ 两处不可能各自漂移，而「两套现实」正是本计划要消灭的。
TIER_ANCHORS = frozenset(
    {
        "§1.3-tier0",  # 机械字段：归档里直接读的键值/计数
        "§1.3-tier1",  # 可观测物证：不经 judge 的确定性计算
        "§1.3-tier2",  # judge 观点 ⇒ 需要边界校准 + 重复抖动两个前置
        "D14",  # Verify 行为层判据机械化（仍出题率=0 为硬条件）
        "D15",  # Memory 分母摊开
        "G1b-revoked",  # Grade 中段分回填撤销 ⇒ 改读 verdict_agreement 辅助位
        "§4.1",  # 机械替身「必要非充分」改名规则
        "§3",  # provenance 八键（字段存在性）
        "§7-②",  # 两极 gold ⇒ ±10 容差无判别力的偏离登记
        "§6-no-archive",  # 该维度无归档证据源 ⇒ 只能未测量
        # ★ 债的标记，不是依据：判据的 tier 与其证据种类不符、已登记待偿（Task 3 registry debt）。
        #   两个 optional 机械替身用它 —— 给它们写 `§1.3-tier2` 等于在 ledger 里声称
        #   「这个数是 judge 观点」，而它们的 fn 全是确定性字符串比较，那句就是假话。
        "TIER-DEBT-task3",
    }
)


def tier_justification(dim: str, spec: dict[str, Any]) -> tuple[str, str]:
    """返回 (来源种类, 说明)。字面量缺锚点 / 锚点不在白名单 ⇒ 抛错，不静默放行。

    ★ registry 侧（判据）由 `predicates.registry.register()` 用同一张 `TIER_ANCHORS` 校验，
      两处共用一份白名单（Task 7 Step 4b 的裁定：两份白名单会各自漂移）。
    """
    derived = spec.get("tier_derived")
    if derived:
        return "registry", f"tier {spec['tier']} 派生自 {derived}"
    anchors = tuple(spec.get("tier_reason") or ())
    if not anchors:
        raise ValueError(
            f"{dim}: 字面量 tier={spec.get('tier')} 必须带 tier_reason"
            "（§1.3 证据种类定义，或 D14/G1b-revoked 等既有降级裁定）"
        )
    unknown = sorted(a for a in anchors if a not in TIER_ANCHORS)
    if unknown:
        raise ValueError(f"{dim}: tier_reason 锚点 {unknown} 不在白名单 {sorted(TIER_ANCHORS)}")
    return "literal", f"tier {spec['tier']} 为字面量，锚点 {'+'.join(anchors)}"


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
