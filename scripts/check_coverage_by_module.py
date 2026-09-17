"""按模块校验覆盖率门槛（backlog #17）。

**为什么需要它**：总覆盖率是**存量指标** —— 它拦得住"整体变差"，
但拦不住"某个模块烂掉、被其它模块的平均值掩盖"。
（这正是本仓库曾经的状态：整体 36% 看着"中等"，而 `retriever.py` 只有 7%。）

**门槛的定位**：设为**略低于当前实测值**，作用是"**防止退步**"，不是"要求达标"。
所以它们应随覆盖率提升而上调，而不是一次定死。
每项后面标注了设定时的实测值，便于日后判断是否需要上调。

用法::

    pytest --cov=src/ --cov-report=json   # 先生成 coverage.json
    python scripts/check_coverage_by_module.py

退出码非 0 表示有模块低于门槛。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 模块 -> (门槛%, 设定时的实测值%)。留 ~3pp 余量，避免正常波动误报。
THRESHOLDS: dict[str, tuple[float, float]] = {
    "rag": (60.0, 63.2),
    "agents": (90.0, 96.7),
    "service": (80.0, 85.1),
}

# 离线数据清洗工具：不参与运行时，codecov.yml 里也已排除，此处同样不计
EXCLUDED = {"tools"}

DEFAULT_JSON = Path("coverage.json")


def load_package_coverage(path: Path) -> dict[str, tuple[int, int]]:
    """从 coverage.json 汇总出每个包的 (语句数, 未覆盖数)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    groups: dict[str, list[int]] = {}
    for file_path, info in data.get("files", {}).items():
        norm = str(file_path).replace("\\", "/")
        parts = norm.split("/")
        pkg = parts[1] if len(parts) > 1 and parts[0] == "src" else "(root)"
        if pkg in EXCLUDED:
            continue
        bucket = groups.setdefault(pkg, [0, 0])
        bucket[0] += int(info["summary"]["num_statements"])
        bucket[1] += int(info["summary"]["missing_lines"])
    return {pkg: (s, m) for pkg, (s, m) in groups.items()}


def evaluate(
    package_coverage: dict[str, tuple[int, int]],
) -> list[tuple[str, float, float, bool]]:
    """返回 [(模块, 实际覆盖率, 门槛, 是否通过)]，只含设了门槛的模块。"""
    results = []
    for pkg, (threshold, _measured) in sorted(THRESHOLDS.items()):
        stats = package_coverage.get(pkg)
        if stats is None:
            results.append((pkg, 0.0, threshold, False))
            continue
        statements, missing = stats
        coverage = (statements - missing) / statements * 100 if statements else 100.0
        results.append((pkg, coverage, threshold, coverage >= threshold))
    return results


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_JSON
    if not path.exists():
        print(f"找不到 {path} —— 请先跑 `pytest --cov=src/ --cov-report=json`")
        return 2

    results = evaluate(load_package_coverage(path))
    failed = []
    print("按模块覆盖率门槛")
    for pkg, coverage, threshold, ok in results:
        mark = "通过" if ok else "**未达标**"
        print(f"  {pkg:<10} {coverage:>6.1f}%  门槛 {threshold:>5.1f}%  {mark}")
        if not ok:
            failed.append(pkg)

    if failed:
        print(f"\n未达标模块: {', '.join(failed)}")
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
