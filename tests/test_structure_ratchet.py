"""结构棘轮：冻结「文件 / 函数规模」现状，阻止**新增**超标代码。

## 为什么需要

`ENGINEERING.md` §2.2 规范 1 定了红线（单文件 ≤600 行、单函数 ≤60 行），
但**此前没有任何机制在执行它** —— 实测 **8 个文件、54 个函数**超标，而且可以继续长。
规范没有执行机制，等于没有规范。

## 规则

- **不在基线里的**文件必须 ≤600 行、函数必须 ≤60 行 —— 新代码一律合规
- **在基线里的**条目以基线值为上限，**只能变小不能变大**（基线必须与实测一致，
  修小之后要同步收紧，否则测试会提醒你）

## 这是棘轮，不是「逼人还清旧债」

与 `ruff` 的 `C90 max-complexity = 30` 同一思路（见 §3.4「门禁设计原则」）：
**旧债按计划逐步还，新债一律不许进。** 一次性把阈值收到 60/600 会让 54 个函数
同时变红，结果必然是被 `noqa` 绕过或被关掉 —— 那就失去了意义。

## 为什么不直接重构掉这 54 个函数

`ENGINEERING.md` §4.2 阶段二把这件事列为 **6–8 周**的工作量；且部分目标
（如 `tools/imputer.py`，含全项目复杂度最高的 `_semantic_segment` = 30）
**单测覆盖率是 0%** —— 没有安全网的重构正是 §1 P0 警告的陷阱。

## 如何更新基线

```bash
python tests/test_structure_ratchet.py      # 重新扫描并写回基线
```

**只在确实改小之后才跑它。** 如果它把某个数值**调大**了，说明代码又变长了 ——
那是回退，应当在 review 里被质疑。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
BASELINE_PATH = Path(__file__).resolve().parent / "_structure_baseline.json"

# 规范 1 的红线（ENGINEERING.md §2.2）
FILE_LIMIT = 600
FUNC_LIMIT = 60


def scan_violations() -> tuple[dict[str, int], dict[str, int]]:
    """扫描 `src/`，返回 (超标文件, 超标函数) 两个 {标识: 行数} 字典。"""
    files: dict[str, int] = {}
    funcs: dict[str, int] = {}

    for path in sorted(SRC.rglob("*.py")):
        key = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8", errors="ignore")

        lines = len(source.splitlines())
        if lines > FILE_LIMIT:
            files[key] = lines

        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover — 语法错误由 pyrefly/ruff 先抓
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = (node.end_lineno or node.lineno) - node.lineno + 1
                if size > FUNC_LIMIT:
                    fkey = f"{key}::{node.name}"
                    funcs[fkey] = max(funcs.get(fkey, 0), size)

    return files, funcs


def load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def baseline() -> dict:
    return load_baseline()


@pytest.fixture(scope="module")
def actual() -> tuple[dict[str, int], dict[str, int]]:
    return scan_violations()


class TestFileSizeRatchet:
    def test_no_new_oversized_file(self, baseline, actual):
        """新文件不得超标；已有超标文件不得再变长。"""
        actual_files, _ = actual
        ceilings: dict[str, int] = baseline["files"]

        offenders = []
        for path, lines in sorted(actual_files.items()):
            ceiling = ceilings.get(path, FILE_LIMIT)
            if lines > ceiling:
                offenders.append(f"{path}: {lines} 行 > 上限 {ceiling}")

        assert not offenders, (
            "以下文件超出规模上限（新文件应 ≤600 行；已有文件只能变小）：\n  "
            + "\n  ".join(offenders)
        )

    def test_baseline_is_not_stale(self, baseline, actual):
        """基线必须与实测一致 —— 修小之后要同步收紧，否则上限会留下空档。"""
        actual_files, _ = actual
        stale = []
        for path, ceiling in sorted(baseline["files"].items()):
            now = actual_files.get(path)
            if now is None:
                stale.append(f"{path}: 已降到 600 行以内，请从基线删除该条目")
            elif now < ceiling:
                stale.append(f"{path}: 实测 {now} 行 < 上限 {ceiling}，请把上限收紧到 {now}")

        assert not stale, (
            "基线过期（棘轮应当收紧）：\n  "
            + "\n  ".join(stale)
            + "\n\n更新方式：python tests/test_structure_ratchet.py"
        )


class TestFunctionSizeRatchet:
    def test_no_new_oversized_function(self, baseline, actual):
        """新函数不得超标；已有超标函数不得再变长。"""
        _, actual_funcs = actual
        ceilings: dict[str, int] = baseline["functions"]

        offenders = []
        for key, size in sorted(actual_funcs.items()):
            ceiling = ceilings.get(key, FUNC_LIMIT)
            if size > ceiling:
                offenders.append(f"{key}: {size} 行 > 上限 {ceiling}")

        assert not offenders, (
            "以下函数超出规模上限（新函数应 ≤60 行；已有函数只能变小）：\n  "
            + "\n  ".join(offenders)
        )

    def test_baseline_is_not_stale(self, baseline, actual):
        _, actual_funcs = actual
        stale = []
        for key, ceiling in sorted(baseline["functions"].items()):
            now = actual_funcs.get(key)
            if now is None:
                stale.append(f"{key}: 已降到 60 行以内，请从基线删除该条目")
            elif now < ceiling:
                stale.append(f"{key}: 实测 {now} 行 < 上限 {ceiling}，请把上限收紧到 {now}")

        assert not stale, (
            "基线过期（棘轮应当收紧）：\n  "
            + "\n  ".join(stale)
            + "\n\n更新方式：python tests/test_structure_ratchet.py"
        )


class TestRatchetIntegrity:
    """守住棘轮本身 —— 门禁坏了会表现为「永远通过」。"""

    def test_limits_match_the_documented_norm(self, baseline):
        """基线的 limits 必须与 §2.2 规范 1 一致，防止有人悄悄放宽红线。"""
        assert baseline["limits"] == {"file": FILE_LIMIT, "function": FUNC_LIMIT}

    def test_baseline_is_not_empty_by_accident(self, baseline):
        """基线被清空会让门禁**变严**（54 个函数立刻变红），不是静默放水 —— 但要能察觉。"""
        assert baseline["files"], "基线 files 为空，疑似被误清空"
        assert baseline["functions"], "基线 functions 为空，疑似被误清空"

    def test_scanner_actually_finds_known_violations(self):
        """元测试：扫描器必须真的能扫出东西，否则「全绿」可能是假绿。

        如果扫描器坏了（路径写错、ast 解析失败），上面的测试会**全部通过** ——
        这正是「保护机制存在 ≠ 生效」。用一个必然超标的真实文件验证。
        """
        files, funcs = scan_violations()
        assert "src/rag/retriever.py" in files, "扫描器没找到已知超标文件，可能已失效"
        assert any("_semantic_segment" in k for k in funcs), "扫描器没找到已知超标函数"


if __name__ == "__main__":  # pragma: no cover — 手动重新生成基线用
    over_files, over_funcs = scan_violations()
    old = load_baseline()
    payload = {
        "_comment": old["_comment"],
        "limits": {"file": FILE_LIMIT, "function": FUNC_LIMIT},
        "files": dict(sorted(over_files.items())),
        "functions": dict(sorted(over_funcs.items())),
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    grew = [
        f"  {k}: {old['files'].get(k, 0)} -> {v}"
        for k, v in payload["files"].items()
        if v > old["files"].get(k, 0)
    ]
    grew += [
        f"  {k}: {old['functions'].get(k, 0)} -> {v}"
        for k, v in payload["functions"].items()
        if v > old["functions"].get(k, 0)
    ]
    print(f"基线已更新：{len(payload['files'])} 文件 / {len(payload['functions'])} 函数")
    if grew:
        print("⚠️ 以下条目**变大了**（属回退，review 时应被质疑）：")
        print("\n".join(grew))
