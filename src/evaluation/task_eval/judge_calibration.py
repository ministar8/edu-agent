"""judge 的人工校准：LLM 分 vs 人工分一致性（从 judge.py 拆出，行为等价）。

★ 阈值（`CALIBRATION_THRESHOLDS`）是「预先约定标准」的落点 —— 不要在别处散落。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 「预先约定标准」——校准通过的四个门槛（提案值，待你最终确认）
CALIBRATION_THRESHOLDS: dict[str, float] = {
    "exact": 0.60,  # 完全同分率
    "within_1": 0.90,  # ±1 分一致率
    "mae_max": 0.50,  # MAE 上限
    "spearman_min": 0.70,  # 秩相关下限
}


@dataclass
class CalibrationReport:
    n: int = 0
    exact: float | None = None
    within_1: float | None = None
    mae: float | None = None
    spearman: float | None = None
    boundary_bias: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    failed_on: list[str] = field(default_factory=list)
    # ★ D6（2026-10-07，登记为 §20.5 #19）：**秩相关的信息量必须自己说出来**。
    #   实测 `calibration_30.jsonl` 的 `human_score` 分布 = `{5: 28, 0: 1, 2: 1}` ⇒
    #   众数占 93.3%，`spearman` 的判别力全在**那 2 行**上（把任一条改成 5 就掉到 ~0.5 FAIL；
    #   把那两行的 judge 分改成 0 却**仍然 PASS**，因为秩相关只看排序不看量级）。
    #   ⇒ 「PASS」可以是真的，但引用它当「judge 与人工秩相关良好」就是过度声称。
    #   ★ 这里**只加露出，不动判定**：阈值（`CALIBRATION_THRESHOLDS`）是「预先约定标准」的落点，
    #     人工分是真实标注 —— 两者都不许为了好看去改（后者等于伪造数据）。
    human_mode: float | None = None
    informative_n: int = 0
    informative_share: float | None = None
    rank_degenerate: bool = False


def _human_dispersion(human: list[float]) -> tuple[float | None, int, float | None]:
    """返回（众数、非众数行数、非众数占比）。占比为 None ⇒ 无可比对样本。"""
    if not human:
        return None, 0, None
    counts: dict[float, int] = {}
    for b in human:
        counts[b] = counts.get(b, 0) + 1
    mode = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    informative = sum(1 for b in human if b != mode)
    return mode, informative, round(informative / len(human), 4)


# 阈值：非众数样本不足 20% ⇒ 秩相关由极少数行决定，必须显式标出（不是判失败，是禁止过度引用）
# ★ 用公开名：`cli` 与护栏都要引用它。原先是私有名，调用方只能跨模块取 `_xxx`（review M5）
#   —— 那是耦合，不是复用。
INFORMATIVE_SHARE_MIN = 0.20


def calibrate(llm_scores: list[float], human_scores: list[float]) -> CalibrationReport:
    """LLM 分 vs 人工分的一致性报告（§决策 #4）。"""
    pairs = [(float(a), float(b)) for a, b in zip(llm_scores, human_scores, strict=False)]
    if not pairs:
        return CalibrationReport()
    n = len(pairs)
    exact = sum(1 for a, b in pairs if a == b) / n
    within_1 = sum(1 for a, b in pairs if abs(a - b) <= 1) / n
    mae = sum(abs(a - b) for a, b in pairs) / n
    rho = _spearman([a for a, _ in pairs], [b for _, b in pairs])
    mode, inf_n, inf_share = _human_dispersion([b for _, b in pairs])
    report = CalibrationReport(
        n=n,
        exact=round(exact, 4),
        within_1=round(within_1, 4),
        mae=round(mae, 4),
        spearman=round(rho, 4) if rho is not None else None,
        boundary_bias=_boundary_bias(pairs),
        human_mode=mode,
        informative_n=inf_n,
        informative_share=inf_share,
        rank_degenerate=(inf_share is not None and inf_share < INFORMATIVE_SHARE_MIN),
    )
    checks = {
        "exact": exact >= CALIBRATION_THRESHOLDS["exact"],
        "within_1": within_1 >= CALIBRATION_THRESHOLDS["within_1"],
        "mae": mae <= CALIBRATION_THRESHOLDS["mae_max"],
        "spearman": (rho is not None) and (rho >= CALIBRATION_THRESHOLDS["spearman_min"]),
    }
    report.failed_on = [k for k, ok in checks.items() if not ok]
    report.passed = not report.failed_on
    return report


def _boundary_bias(pairs: list[tuple[float, float]]) -> dict[str, float]:
    """0/1/5 三个边界档上的「LLM − 人工」平均偏差（正 = judge 偏高）。"""
    out: dict[str, float] = {}
    for level in (0.0, 1.0, 5.0):
        sel = [a - b for a, b in pairs if b == level]
        if sel:
            out[str(int(level))] = round(sum(sel) / len(sel), 3)
    return out


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman 秩相关（不引入 scipy：秩相关 = 秩上的 Pearson）。常数序列 → None。"""
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _ranks(values: list[float]) -> list[float]:
    """平均秩（并列取平均）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks
