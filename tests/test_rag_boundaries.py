"""包间硬边界护栏（AST 静态扫描，不执行任何模块）。

来源：2026-11-07 实测 import 图审计（docs/RAG_BOUNDARY_MAP.md §10）。
这些边界是**当测为真**的架构不变量；若测试失败，说明出现了越界依赖，
必须先确认是有意设计（更新本文件与边界地图）还是误引（修 import）。

锁定的五条硬边界（来源 = 2026-11-07 实测 import 图）：

1. ``rag`` 不 import ``agents`` / ``service`` / ``evaluation`` / ``db``
   （rag 是被消费方；评测反向依赖它，rag 自身保持纯净）。
   允许：``document_processing``（离线清洗复用）、``prompts``（在线 LLM 提示词）。
2. ``infra`` 只能 import ``{core, schema}`` + 第三方库——它是存储/遥测底座，
   **禁止**向 rag / agents / memory / service / evaluation / prompts / db 反向依赖。
3. ``core`` 不得 import ``{infra, rag, agents, memory, prompts, service, evaluation}``
   —— core 是项目最底层，只能向下依赖 schema 和第三方库。
4. ``memory`` 使用 ``rag`` 的文件**登记制**：新文件加 import 即失败，
   须先在 ``MEMORY_RAG_ALLOWED`` 登记语义背景（当前 1 个：topics.py 的 SYNONYM_MAP 兜底）。
   ``sqlite.py`` 已改走 ``infra.embeddings``，不再 import rag，故从清单移除。
5. ``agents`` 使用 ``rag`` 的文件**登记制**：
   ``tools`` 是检索主通道；``teaching_graph`` 只取任务分类——每一个都有明确语义。
   ``grading.py`` 已改走 ``core.llm_calls``，不再 import rag，故从清单移除。
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

# 登记清单（实测当真为白名单；新增 = 有意设计，须在此写明语义）
RAG_UPPER_FORBIDDEN = {"agents", "service", "evaluation", "db"}
INFRA_ALLOWED = {"core", "schema"}
CORE_FORBIDDEN = {"infra", "rag", "agents", "memory", "prompts", "service", "evaluation", "db"}
MEMORY_RAG_ALLOWED = {
    # 同义词兜底：weak_topics 归一化取 SYNONYM_MAP 的 canonical 过滤子集
    "memory/topics.py",
}
AGENTS_RAG_ALLOWED = {
    # 检索主通道：3 个检索工具工厂 + 出题/批改工具 + RAG 错误映射
    "agents/runtime/tools.py",
    # 编排任务分类：prepare_task 需要 task mode（懒加载单点）
    "agents/orchestration/teaching_graph.py",
}

VIOLATIONS: list[str] = []


def _top_package(node: ast.Ast, imports: list[str]) -> None:
    """收集一条 import 语句的顶层包名（from X import Y / import X）。"""
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports.append(alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        imports.append(node.module.split(".")[0])


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    tops: list[str] = []
    for node in ast.walk(tree):
        _top_package(node, tops)
    return tops


def _collect(pkg: str) -> list[Path]:
    return sorted((SRC / pkg).rglob("*.py"))


def _check(describer: str, allow: bool, detail: str) -> None:
    if not allow:
        VIOLATIONS.append(f"{describer}: {detail}")


def test_rag_never_imports_upper_layers() -> None:
    for p in _collect("rag"):
        for top in _imports_of(p):
            _check(
                str(p.relative_to(SRC)),
                top not in RAG_UPPER_FORBIDDEN,
                f"rag 不得 import {top}",
            )
    assert not VIOLATIONS, "\n".join(VIOLATIONS)


def test_memory_imports_rag_only_via_registered() -> None:
    for p in _collect("memory"):
        rel = p.relative_to(SRC).as_posix()
        for top in _imports_of(p):
            _check(
                rel,
                top != "rag" or rel in MEMORY_RAG_ALLOWED,
                f"memory 使用 rag 须登记（未登记文件 {rel}）",
            )
    assert not VIOLATIONS, "\n".join(VIOLATIONS)


def test_document_processing_is_closed() -> None:
    for p in _collect("document_processing"):
        for top in _imports_of(p):
            _check(
                str(p.relative_to(SRC)),
                top != "rag",
                "document_processing 不得 import rag（封闭纯计算层）",
            )
    assert not VIOLATIONS, "\n".join(VIOLATIONS)


def test_agents_touches_rag_only_via_registered() -> None:
    for p in _collect("agents"):
        rel = p.relative_to(SRC).as_posix()
        for top in _imports_of(p):
            _check(
                rel,
                top != "rag" or rel in AGENTS_RAG_ALLOWED,
                f"agents 使用 rag 须登记（未登记文件 {rel}）",
            )
    assert not VIOLATIONS, "\n".join(VIOLATIONS)


def test_infra_only_imports_core_schema_third_party() -> None:
    """infra 是存储/遥测底座，只能向 core / schema / 第三方库依赖。"""
    for p in _collect("infra"):
        rel = p.relative_to(SRC).as_posix()
        for top in _imports_of(p):
            _check(
                rel,
                top in INFRA_ALLOWED or top not in {"agents", "service", "evaluation", "memory", "prompts", "rag", "db", "document_processing"},
                f"infra 禁止向业务包反向依赖（{rel} import {top}）",
            )
    assert not VIOLATIONS, "\n".join(VIOLATIONS)


def test_core_does_not_import_business_layers() -> None:
    """core 是项目最底层，不得 import infra / rag / 业务包。"""
    for p in _collect("core"):
        rel = p.relative_to(SRC).as_posix()
        for top in _imports_of(p):
            _check(
                rel,
                top not in CORE_FORBIDDEN,
                f"core 不得 import {top}（{rel}）",
            )
    assert not VIOLATIONS, "\n".join(VIOLATIONS)
