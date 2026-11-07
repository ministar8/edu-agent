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
6. ``evaluation`` 使用 ``rag.retrieval.*`` 的文件**登记制**：
   从 ``rag.retrieval`` 顶层门面导入（contract symbols：`EvidenceBundle` /
   `FusedEvidence` / `TextEvidence` / `aretrieve_evidence_raw` / `retrieve_for_task`）
   放行；深层路径（`rag.retrieval.evidence_policy`、`rag.retrieval.task_policy`、
   猴子补丁 `rag.retrieval.pipeline._stages` 等）须在
   ``EVALUATION_RAG_ALLOWED`` 登记语义背景。
7. 集合身份（``SUBJECT_COLLECTIONS`` 等）**唯一定义于** ``rag/retrieval/collections.py``
   （T4 收口，2026-11-07）：其他文件只允许 import / 别名引用，不得另行赋值——
   原两处散装定义（``recall_collections`` 与 ``layer_recall`` 的含 exams 5 元组）曾各自漂移。
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
EVALUATION_RAG_ALLOWED = {
    # 猴子补丁：阶段追踪需在 rag 内部命名空间打补丁（边界地图 §7-3/§7-4 已明文登记）
    "evaluation/diagnostics/_stage_trace_core.py",
    "evaluation/probe_tracing.py",
    # 模块级消费：诊断/门禁直接操作 rag 内部语义单元
    "evaluation/diagnostics/candidate_trace.py",
    # 策略函数：不进 rag.retrieval 顶层门面，留在 deep import 登记
    "evaluation/task_eval/retrieval_probe.py",
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
    """收集一条 import 语句的顶层包名（兼容旧调用）。"""
    return [top for top, _, _ in _imports_detail_of(path)]


def _imports_detail_of(path: Path) -> list[tuple[str, str | None, str | None]]:
    """收集 import 的 (顶层包, 子模块, 完整模块路径)。

    例如：
    - ``from rag.retrieval import X`` → ("rag", "retrieval", "rag.retrieval")
    - ``from rag.retrieval.evidence import X`` → ("rag", "retrieval.evidence", "rag.retrieval.evidence")
    - ``import rag.retrieval.retriever as R`` → ("rag", "retrieval.retriever", "rag.retrieval.retriever")
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    out: list[tuple[str, str | None, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                out.append((parts[0], ".".join(parts[1:]) if len(parts) > 1 else None, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            parts = node.module.split(".")
            out.append((parts[0], ".".join(parts[1:]) if len(parts) > 1 else None, node.module))
    return out


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


def test_evaluation_imports_rag_only_via_registered() -> None:
    """evaluation 使用 rag.retrieval.* 的文件须登记。

    从 ``rag.retrieval`` 顶层门面导入（contract symbols：EvidenceBundle /
    FusedEvidence / TextEvidence / aretrieve_evidence_raw / retrieve_for_task）
    放行；深层路径（submodule 或猴子补丁，如 rag.retrieval.pipeline._stages、
    rag.retrieval.task_policy）须在 ``EVALUATION_RAG_ALLOWED`` 登记。
    """
    for p in _collect("evaluation"):
        rel = p.relative_to(SRC).as_posix()
        for top, sub, full in _imports_detail_of(p):
            if top != "rag":
                continue
            # 从 rag.retrieval 顶层门面导入：放行（contract symbols）
            if sub == "retrieval" and full == "rag.retrieval":
                continue
            # 深层路径：须登记
            if full and full.startswith("rag.retrieval."):
                _check(
                    rel,
                    rel in EVALUATION_RAG_ALLOWED,
                    f"evaluation 使用 {full} 须登记（未登记文件 {rel}）",
                )
    assert not VIOLATIONS, "\n".join(VIOLATIONS)


# ── 8. 集合身份唯一登记处（T4，2026-11-07）─────────────────────────────

# 这些名字只允许在 `rag/retrieval/collections.py` 里被赋值；其他文件 import 可以，赋值不行。
COLLECTION_IDENTITY_NAMES = {
    "SUBJECT_COLLECTIONS",
    "EXAMS_COLLECTION",
    "LEARNING_PATHS_COLLECTION",
    "CODE_COLLECTION",
    "COLLECTION_KEYWORDS",
    "ALL_COLLECTIONS",
}
_REGISTRY_PATH = SRC / "rag" / "retrieval" / "collections.py"


def _assigned_names(path: Path) -> set[str]:
    """AST 找出文件中所有对集合身份名字的赋值目标（含 AnnAssign / 元组展开目标）。"""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names: set[str] = set()

    def _targets(t: ast.expr) -> None:
        if isinstance(t, ast.Name):
            names.add(t.id)
        elif isinstance(t, ast.Tuple | ast.List):
            for el in t.elts:
                _targets(el)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                _targets(t)
        elif isinstance(node, ast.AnnAssign):
            _targets(node.target)
        elif isinstance(node, ast.AugAssign):
            _targets(node.target)
    return names


def test_collection_identities_defined_only_in_collections() -> None:
    """集合身份单点定义（T4 锁）：任何其他文件的赋值都说明登记处被绕开。

    import / 别名引用（如 ``SUBJECT_TO_COLLECTION = CODE_COLLECTION`` 的消费侧改名）
    不算赋值违规——只拦字面重新定义。"""
    offenders: list[str] = []
    for p in sorted(SRC.rglob("*.py")):
        if p == _REGISTRY_PATH:
            continue
        hit = _assigned_names(p) & COLLECTION_IDENTITY_NAMES
        if hit:
            offenders.append(f"{p.relative_to(SRC)}: {'、'.join(sorted(hit))}")
    assert not offenders, "集合身份必须只在 rag/retrieval/collections.py 定义：\n" + "\n".join(offenders)
