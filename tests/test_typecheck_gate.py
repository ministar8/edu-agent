"""类型检查门禁的配置守卫（backlog #12）。

**为什么需要它**：`pyrefly` 的豁免配置是**纯文本**，改错了不会有任何提示 ——
把 `unbound-name` 加回豁免列表，检查就**静默失效**，而 CI 依然"通过"。
这与本项目反复遇到的一类问题同构：**保护机制自己坏掉，没人会发现。**

本组把「这两个检查必须保持开启」和「可选依赖必须显式标注」钉住。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

# 这两个检查是 backlog #12 明确要求开启的
REQUIRED_ENABLED = ("unbound-name", "missing-import")


def _sub_configs() -> list[dict]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["pyrefly"].get("sub-config", [])


def _disabled_errors() -> dict[str, set[str]]:
    """matches 模式 -> 被显式关掉的错误码集合。"""
    out: dict[str, set[str]] = {}
    for cfg in _sub_configs():
        errors = cfg.get("errors", {})
        out[cfg["matches"]] = {code for code, enabled in errors.items() if enabled is False}
    return out


class TestRequiredChecksStayEnabled:
    def test_no_sub_config_exempts_required_checks(self):
        """**任何** sub-config 都不得豁免这两个检查 —— 不只是 `src/rag/**`。

        `unbound-name` 在两个目录各查出一个真问题：
        `src/rag/semantic_cache.py` 的未绑定 `mgr`、
        `src/tools/imputer.py` 的 `tokenizer = jieba` 之后用 `jieba.cut()`。
        豁免任何一个目录，都会让同类问题重新藏起来。
        """
        disabled = _disabled_errors()
        assert disabled is not None
        for matches, codes in disabled.items():
            for code in REQUIRED_ENABLED:
                assert code not in codes, (
                    f"`{code}` 被 `{matches}` 的豁免列表关掉了。\n"
                    f"它会抓真错误（已在 rag 与 tools 各查出一处），"
                    f"不要为了消噪音关掉它 —— 应显式标注具体的导入/变量。"
                )

    def test_rag_and_tools_exemptions_still_exist(self):
        """豁免本身应保留（其它错误码仍需放宽），只是不能包含这两个。"""
        disabled = _disabled_errors()
        assert "src/rag/**" in disabled, "src/rag/** 的豁免配置不见了"
        assert "src/tools/**" in disabled, "src/tools/** 的豁免配置不见了"

    def test_exemption_lists_are_not_empty_of_justification(self):
        """豁免必须真的在关东西 —— 空豁免表意味着配置写错了。"""
        disabled = _disabled_errors()
        assert disabled, "没有任何豁免配置，说明 pyproject 结构变了"

    def test_config_parses(self):
        assert _sub_configs(), "[tool.pyrefly.sub-config] 未解析出来"


class TestOptionalImportsAreAnnotated:
    """可选依赖的导入必须显式标注 —— 否则 `missing-import` 开不起来。"""

    # (文件, 模块名)
    OPTIONAL = [
        ("src/evaluation/adapters.py", "ragas"),
        ("src/evaluation/ragas_eval.py", "ragas"),
        ("src/evaluation/ragas_eval.py", "datasets"),
        ("src/rag/loader.py", "cchardet"),
    ]

    def test_each_optional_import_has_type_ignore(self):
        for rel, module in self.OPTIONAL:
            text = (ROOT / rel).read_text(encoding="utf-8")
            pattern = re.compile(
                rf"^\s*(from|import)\s+{re.escape(module)}[^\n]*#\s*type:\s*ignore\[import-not-found\]",
                re.MULTILINE,
            )
            assert pattern.search(text), (
                f"{rel} 里 `{module}` 的导入没有 `# type: ignore[import-not-found]`。\n"
                f"它是可选的 eval 依赖（CI 不装），不加标注会让 `missing-import` 报错，"
                f"进而逼人把整个检查关掉 —— 那样就抓不到模块名拼写错误了。"
            )

    def test_optional_modules_are_declared_as_optional(self):
        """被标注的模块要么在可选依赖组里，要么明确是运行期兜底（如 cchardet）。"""
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        eval_group = data.get("dependency-groups", {}).get("eval", [])
        assert any("ragas" in dep for dep in eval_group), "ragas 应留在 eval 组（可选）"
        assert any("datasets" in dep for dep in eval_group), "datasets 应留在 eval 组（可选）"
        # 主依赖里不应出现它们 —— 否则标注的理由就不成立了
        main_deps = data["project"]["dependencies"]
        assert not any("ragas" in dep for dep in main_deps), "ragas 不该进主依赖"
