"""`scripts/check_coverage_by_module.py` 的测试（backlog #17）。

**为什么给一个"检查脚本"写测试**：它是**门禁本身**。门禁如果坏了（比如读错字段、
算错百分比、失败时不返回非 0），表现是"**永远通过**" —— 没人会发现，
直到某个模块烂掉很久之后。这类"静默失效的守卫"必须自己有测试。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_coverage_by_module as C  # noqa: E402


def _write_json(tmp_path: Path, files: dict[str, tuple[int, int]]) -> Path:
    """files: {路径: (语句数, 未覆盖数)}"""
    payload = {
        "files": {
            path: {"summary": {"num_statements": s, "missing_lines": m}}
            for path, (s, m) in files.items()
        }
    }
    out = tmp_path / "coverage.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


class TestLoadPackageCoverage:
    def test_groups_by_package(self, tmp_path):
        p = _write_json(
            tmp_path,
            {
                "src/rag/a.py": (100, 40),
                "src/rag/b.py": (100, 20),
                "src/service/c.py": (100, 10),
            },
        )
        groups = C.load_package_coverage(p)
        assert groups["rag"] == (200, 60)
        assert groups["service"] == (100, 10)

    def test_windows_paths_handled(self, tmp_path):
        """coverage.json 在 Windows 上写的是反斜杠路径 —— 解析必须兼容。"""
        p = _write_json(tmp_path, {"src\\rag\\a.py": (100, 50)})
        assert C.load_package_coverage(p)["rag"] == (100, 50)

    def test_excluded_packages_skipped(self, tmp_path):
        """`tools/` 是离线工具，codecov 已排除，这里也必须排除。"""
        p = _write_json(tmp_path, {"src/tools/imputer.py": (1000, 1000), "src/rag/a.py": (100, 0)})
        groups = C.load_package_coverage(p)
        assert "tools" not in groups

    def test_root_level_files_grouped_by_filename(self, tmp_path):
        """`src/` 下直接放的文件（如 `run_service.py`）没有包名，按文件名单独成组。"""
        p = _write_json(tmp_path, {"src/run_service.py": (10, 10)})
        groups = C.load_package_coverage(p)
        assert "run_service.py" in groups

    def test_paths_outside_src_go_to_root_bucket(self, tmp_path):
        p = _write_json(tmp_path, {"weird.py": (10, 10)})
        assert "(root)" in C.load_package_coverage(p)


class TestEvaluate:
    def test_passing_module(self):
        results = C.evaluate({"rag": (100, 30)})  # 70%
        rag = [r for r in results if r[0] == "rag"][0]
        assert rag[3] is True

    def test_failing_module(self):
        results = C.evaluate({"rag": (100, 60)})  # 40% < 60% 门槛
        rag = [r for r in results if r[0] == "rag"][0]
        assert rag[3] is False

    def test_exactly_at_threshold_passes(self):
        """刚好等于门槛应算通过 —— 边界写成 `>` 会让"刚好达标"变成失败。"""
        threshold = C.THRESHOLDS["rag"][0]
        statements = 1000
        missing = int(statements * (100 - threshold) / 100)
        results = C.evaluate({"rag": (statements, missing)})
        rag = [r for r in results if r[0] == "rag"][0]
        assert rag[1] == pytest.approx(threshold, abs=0.1)
        assert rag[3] is True

    def test_missing_module_is_treated_as_failure(self):
        """模块整个消失（比如被误删）必须报失败，而不是静默跳过。"""
        results = C.evaluate({})
        assert all(r[3] is False for r in results)

    def test_all_configured_modules_are_reported(self):
        results = C.evaluate({})
        assert {r[0] for r in results} == set(C.THRESHOLDS)

    def test_zero_statements_does_not_divide_by_zero(self):
        results = C.evaluate({"rag": (0, 0)})
        rag = [r for r in results if r[0] == "rag"][0]
        assert rag[1] == 100.0


class TestMain:
    def test_missing_file_returns_2(self, tmp_path):
        assert C.main(["prog", str(tmp_path / "nope.json")]) == 2

    def test_all_pass_returns_0(self, tmp_path, capsys):
        p = _write_json(tmp_path, {"src/rag/a.py": (100, 0), "src/agents/a.py": (100, 0)})
        # service 缺失 → 会失败；这里只放够了的模块，故补一个 service
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["files"]["src/service/a.py"] = {
            "summary": {"num_statements": 100, "missing_lines": 0}
        }
        p.write_text(json.dumps(payload), encoding="utf-8")
        assert C.main(["prog", str(p)]) == 0

    def test_regression_returns_1(self, tmp_path):
        p = _write_json(tmp_path, {"src/rag/a.py": (100, 100)})  # rag 0%
        assert C.main(["prog", str(p)]) == 1

    def test_output_lists_each_module(self, tmp_path, capsys):
        p = _write_json(tmp_path, {"src/rag/a.py": (100, 0)})
        C.main(["prog", str(p)])
        out = capsys.readouterr().out
        for pkg in C.THRESHOLDS:
            assert pkg in out


class TestThresholdsAreSane:
    def test_thresholds_are_below_measured_values(self):
        """门槛必须低于设定时的实测值 —— 否则它一上来就是红的。

        这条测试也提醒维护者：**覆盖率提升后应上调门槛**，
        而不是让它永远停在"防止退步"的最低线上。
        """
        for pkg, (threshold, measured) in C.THRESHOLDS.items():
            assert threshold < measured, f"{pkg} 的门槛({threshold}) 不低于实测值({measured})"

    def test_headroom_is_not_excessive(self):
        """余量过大等于没有门槛。"""
        for pkg, (threshold, measured) in C.THRESHOLDS.items():
            assert measured - threshold <= 10.0, (
                f"{pkg} 的门槛余量过大（{measured - threshold:.1f}pp）"
            )
