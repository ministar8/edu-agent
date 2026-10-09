"""核对 `docs/EXPERIMENTS.md` §20.7.1 登记的六条基线重录 diff 是否**穷尽且逐值属实**（只读，零 token）。

为什么需要它（收尾修复批 Important-4）：§20.7.1 曾以「主要 diff」的措辞**挑显著的写**，
先后漏过 `category_precision`（fake+off −0.0012 / real+off +0.0019 / fake+disabled +0.0048）
等非零格 ⇒ 「全量重算」名不副实。人工登记会漏，机器不会累 —— 本脚本把「登记 = 工件」
变成一条可重跑的机械核对：

1. **工件 → 文档**：两代基线（`evals/baselines/pre_task9_20261009/` ↔ `evals/baselines/`）
   逐指标相减，**每一个非零 diff** 都必须出现在 §20.7.1 对应行、且数值一致；
2. **文档 → 工件**：文档里写的**每一个 diff** 都必须能在工件里核到，且数值一致
   （写错一位小数也是红）。

口径：
- diff 一律 `round(new − old, 4)`，与基线 `as_dict()` 的 4 位舍入同口径；非零 = 登记义务。
- 文档简写（`precision` / `count` / `hit@1` …）经 `_DOC_ALIAS` 映射回工件键名；
  出现**未知简写**同样 exit 1（别名表就是这两套名字的唯一桥，扩充它必须对着工件键表扩）。
- ★ 本脚本是**验证工具**，不是门禁判据：不进 `evidence_chain_gate`、不动 `_EXPECTED_ITEMS`。

用法::

    PYTHONIOENCODING=utf-8 uv run python scripts/check_baseline_diff_registration.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "EXPERIMENTS.md"
OLD_DIR = ROOT / "evals" / "baselines" / "pre_task9_20261009"
NEW_DIR = ROOT / "evals" / "baselines"

# §20.7.1 表格行的别名 → 基线 `metrics` 的工件键（唯一一座桥，扩充须对着工件键表扩）。
_DOC_ALIAS: dict[str, str] = {
    "category_hit_at_1": "category_hit_at_1",
    "category_hit@1": "category_hit_at_1",
    "hit@1": "category_hit_at_1",
    "category_hit_at_k": "category_hit_at_k",
    "category_hit@k": "category_hit_at_k",
    "category_mrr": "category_mrr",
    "category_precision": "category_precision",
    "precision": "category_precision",
    "kp_hit_at_k": "kp_hit_at_k",
    "kp_hit@k": "kp_hit_at_k",
    "kp_mrr": "kp_mrr",
    "mean_evidence_count": "mean_evidence_count",
    "count": "mean_evidence_count",
    "empty_result_rate": "empty_result_rate",
    "kp_annotated": "kp_annotated",
}

# 六条路由的基线文件名（与 §20.7.1 首列反引号里的名字逐字一致）。
_BASELINE_FILES = [
    "retrieval_baseline.json",
    "retrieval_baseline_rerank.json",
    "retrieval_baseline_fake_disabled.json",
    "retrieval_baseline_real_embed.json",
    "retrieval_baseline_real_disabled.json",
    "retrieval_baseline_real_rerank.json",
]

# `category_precision +0.0048` / `**kp_mrr −0.0198**` / `count −0.0256`：
# 数值前允许 markdown 粗体星号；负号同时接受 U+2212 与 ASCII hyphen。
_DIFF_RE = re.compile(r"([A-Za-z][A-Za-z0-9@_]*?)\s*(\*\*)?\s*([+−-])\s*(\d+\.\d+)")
_NUM = 4


def _section(text: str) -> str:
    """切出 §20.7.1 一节（到 §20.7.2 为止）。找不到即报错——宁可不跑，不许静默空扫。"""
    start = text.index("### 20.7.1")
    rest = text[start + len("### 20.7.1") :]
    end = rest.find("### 20.7.2")
    if end == -1:
        raise SystemExit("找不到 §20.7.1 的结束边界（### 20.7.2）—— 节结构变了，请人工核对")
    return rest[:end]


def _row_for(section: str, fname: str) -> str:
    """表格里以反引号文件名标识的那一行；找不到即报错（六行是登记义务的一部分）。"""
    for line in section.splitlines():
        if line.startswith("|") and f"`{fname}`" in line:
            return line
    raise SystemExit(f"§20.7.1 表格里找不到 `{fname}` 对应的行")


def _parse_claims(row: str) -> dict[str, float]:
    """从行里抽出全部「别名 ±数值」。只认第二列（diff 列）——归因列不含 diff。"""
    cells = row.split("|")
    if len(cells) < 4:
        raise SystemExit(f"表格行竖线数异常（<4 列）：{row[:60]}…")
    diff_cell = "|".join(cells[2:-1])  # 第一列=路由，最后一列=归因（含证据），其余并入 diff 列
    claims: dict[str, float] = {}
    for m in _DIFF_RE.finditer(diff_cell):
        name, _, sign, num = m.groups()
        key = _DOC_ALIAS.get(name)
        if key is None:
            raise SystemExit(
                f"未知指标简写 `{name}`（不在 _DOC_ALIAS）—— 对着工件键表补别名，不许猜"
            )
        value = float(num) * (-1 if sign == "−" or sign == "-" else 1)
        claims[key] = round(value, _NUM)
    return claims


def _metrics(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))["metrics"]


def main() -> int:
    problems: list[str] = []
    try:
        section = _section(DOC.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"[拒绝] 文档节定位失败：{e}")
        return 2

    for fname in _BASELINE_FILES:
        old_p, new_p = OLD_DIR / fname, NEW_DIR / fname
        if not old_p.exists() or not new_p.exists():
            print(f"[拒绝] 基线工件缺失：{old_p if not old_p.exists() else new_p}")
            return 2
        old_m, new_m = _metrics(old_p), _metrics(new_p)
        keys = sorted(set(old_m) | set(new_m))
        computed: dict[str, float] = {}
        for k in keys:
            if k == "n_queries":  # 条数不是质量指标；两代实测都是 156，不同则本来就是事故
                if old_m.get(k) != new_m.get(k):
                    problems.append(f"{fname}：n_queries 两代不同（{old_m.get(k)}→{new_m.get(k)}）")
                continue
            if k not in old_m or k not in new_m:
                problems.append(
                    f"{fname}：指标 `{k}` 只存在于一代（{old_m.get(k)}→{new_m.get(k)}）"
                )
                continue
            d = round(float(new_m[k]) - float(old_m[k]), _NUM)
            if d != 0:
                computed[k] = d
        claims = _parse_claims(_row_for(section, fname))

        # 方向 1：工件里每个非零 diff 都出现在该行（穷尽性 —— 「主要 diff」就是从这里漏的）
        for k, d in computed.items():
            if k not in claims:
                problems.append(f"{fname}：工件非零 diff `{k} {d:+.4f}` **未登记**进 §20.7.1 行")
            elif abs(claims[k] - d) > 1e-9:
                problems.append(f"{fname}：`{k}` 登记为 {claims[k]:+.4f}，工件算出来是 {d:+.4f}")
        # 方向 2：文档里每个 diff 都能在工件核到（真实性，含写了个工件里为零的差值）
        for k, c in claims.items():
            if k not in computed:
                problems.append(
                    f"{fname}：文档登记 `{k} {c:+.4f}` 在工件里**核不到**（该键 diff 为零或不存在）"
                )

    for fname in _BASELINE_FILES:
        print(f"—— {fname}：核对完毕")
    if problems:
        print(f"\n[不一致] {len(problems)} 处：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        "\n[一致] §20.7.1 六行 × 全部指标：工件的每个非零 diff 均已登记、"
        "登记的每个 diff 均与工件逐值吻合（两向核对，无抽查）。"
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
