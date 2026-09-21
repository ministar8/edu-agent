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
    "rag": (71.0, 74.3),
    "agents": (90.0, 96.7),
    "service": (80.0, 85.1),
}

# 整包排除：离线数据清洗工具，不参与运行时，codecov.yml 里也已排除
EXCLUDED = {"tools"}

# 模块级排除：只从**所属包的门槛**里摘出去（模块本身仍出现在覆盖率报告里）。
# 路径以 `src/` 开头，与 coverage.json 的 key 一致。
#
# ★ 为什么离线入库链可以排除 —— 它们**不是没有保护，而是保护机制不是单测**：
#   `evaluation.retrieval_gate.build_index()` 刻意复用真实入库链路
#   （load → clean → split → enhance → tag → add），每次 CI 都在真实 `knowledge/`
#   语料上端到端跑一遍（约 2200 chunks）。内容被洗坏、切错、标签打歪，都会让
#   门禁指标漂移并失败。再用单测覆盖一遍是同一条链路的重复投入。
#
# ⚠️ **这个前提有守卫**：`tests/evaluation/test_retrieval_gate.py` 的
#   `TestBuildIndexUsesRealPipeline` 断言 build_index 必须依次调用链路每一步。
#   有人把它换成评测专用旁路时那条测试会红 —— 否则这里的排除就是**没有依据的**
#   （排除照旧、指标照旧绿，但保护已经没了：典型的「保护机制存在 ≠ 生效」）。
#
# 连带效果：排除后 `rag` 口径从 68.4% 升到 74.3%，门槛因此可以从 60% 抬到 71%
# —— 用「不再重复覆盖离线链」换来「对运行时路径更严的守住」。
EXCLUDED_MODULES: frozenset[str] = frozenset(
    {
        "src/rag/loader.py",
        "src/rag/cleaner.py",
        "src/rag/enhancer.py",
        "src/rag/knowledge_tagger.py",
        "src/rag/ingest.py",
    }
)

DEFAULT_JSON = Path("coverage.json")


def load_package_coverage(path: Path) -> dict[str, tuple[int, int]]:
    """从 coverage.json 汇总出每个包的 (语句数, 未覆盖数)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    groups: dict[str, list[int]] = {}
    for file_path, info in data.get("files", {}).items():
        norm = str(file_path).replace("\\", "/")
        parts = norm.split("/")
        pkg = parts[1] if len(parts) > 1 and parts[0] == "src" else "(root)"
        if pkg in EXCLUDED or norm in EXCLUDED_MODULES:
            continue
        bucket = groups.setdefault(pkg, [0, 0])
        bucket[0] += int(info["summary"]["num_statements"])
        bucket[1] += int(info["summary"]["missing_lines"])
    return {pkg: (s, m) for pkg, (s, m) in groups.items()}


def missing_excluded_modules(path: Path) -> list[str]:
    """``EXCLUDED_MODULES`` 里写了、但覆盖率报告里不存在的路径。

    防的是「路径打错 → 排除静默失效」：那种情况下门槛会因口径不符而报红，
    但信息指向"覆盖率不达标"，会让人往错的方向查 —— 所以单独报出来。
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    present = {str(key).replace("\\", "/") for key in data.get("files", {})}
    return sorted(EXCLUDED_MODULES - present)


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

    missing = missing_excluded_modules(path)
    if missing:
        print("[警告] EXCLUDED_MODULES 里以下路径不在覆盖率报告中（拼错了？）：")
        for name in missing:
            print(f"  - {name}")
        print("       排除会静默失效，本次门槛按「未排除」口径计算。\n")

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
