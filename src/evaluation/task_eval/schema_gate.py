"""V0：正式实验的前置闸（EVIDENCE_CHAIN.md §8）。

★ 阻塞范围刻意划清：只拦「把未证明的东西当成绩」，不拦「披露为 limitation」。
  否则本方案会在答辩日之前把自己锁死。

两条拦网（§8 的 V0 行，逐字对应）：
  ① schema 完整性 —— 判据声明的 `contract_inputs` 必须在归档里**键真实存在**，
     且禁止用 `.get(k, False)` / `.get(k, 0)` 把「缺字段」掩盖成「测过了、值为假」
     （AST 扫描，沿用 `memory_step4fix_gate` 已有的 AST 手法）；
     `gold_source_ref` 缺失的 gold 视为**未填**（§8① 末句）。
  ② 未测量判据禁进门槛 —— `claim → required predicates → 全部 missing_premise`
     ⇒ claim = unmeasurable ⇒ 禁止作为正式效果章的门槛行。
     这就是 §4.2 事故（`gen_case_pass = 1.000` 而 correctness/answerability/difficulty
     全 missing）的机械拦网，也是 G1a 排在 P0 之前的原因。
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation.task_eval.predicates import registry
from evaluation.task_eval.predicates.common import has_path, is_reply_part

# ★ 这里**不写**任何硬编码的 required 名单（旧稿有 `REQUIRED_BY_TASK`，里面还留着已改名的
#   `gen_answerability`）：required 集合必须从 registry 推导，否则就存在第二套真源，
#   下次改名时 V0 会去查一个不存在的判据名 —— 于是刚做的「防冒充」改名反而被 V0 绕过。
_MASKING_DEFAULTS: frozenset[str] = frozenset({"False", "True", "0", "0.0", '""', "''", "[]", "{}"})


def required_predicates(task: str) -> list[str]:
    """registry 里该任务下**非 optional** 的判据名，就是 required 集合的唯一来源。"""
    return [p.name for p in registry.for_task(task) if not p.optional]


def gate_rejects(verdicts: dict[str, str], *, task: str = "generate") -> bool:
    """任一 required 项 `missing_premise` ⇒ 该 claim 禁止作为门槛行。"""
    return any(verdicts.get(name) == "missing_premise" for name in required_predicates(task))


def unmeasurable_required(records: list[dict[str, Any]], *, task: str) -> list[str]:
    """该任务 required（非 optional）判据里，在归档上**全部** missing_premise（n_measured=0）的名字。
    §8②：claim → required predicates → 全缺 ⇒ claim unmeasurable ⇒ 禁止进正式效果章门槛行。
    """
    recs = [r for r in records if str(r.get("task") or "") == task]
    if not recs:
        return []
    out: list[str] = []
    for pred in registry.for_task(task):
        if pred.optional:
            continue
        verdicts = [pred.fn(r) for r in recs]
        if all(v == "missing_premise" for v in verdicts):
            out.append(pred.name)
    return sorted(out)


def unmeasurable_tasks(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    """按任务汇总 §8② 的不可测 required 判据（只遍历**有判据**的任务）。

    `qa` / `grade` 走 metrics 路径、registry 里无判据 ⇒ 不出现在结果里；
    这里的「无判据」是设计（见 `registry.for_task` 的 docstring），不是缺字段。
    """
    out: dict[str, list[str]] = {}
    for task in sorted({str(r.get("task") or "") for r in records}):
        if not required_predicates(task):
            continue
        names = unmeasurable_required(records, task=task)
        if names:
            out[task] = names
    return out


def check_archive_records(records: list[dict[str, Any]]) -> list[str]:
    """判据声明的 `contract_inputs` 必须在 record 里**真实存在**。

    两类地址分别处理（语法见 Task 3 的 `common.has_path`）：
      - `reply#片段` ⇒ 不查键（它不是键），由 Task 5 的 R1-A 覆盖检查负责；
      - 点分路径（含 `top_items[].x`）⇒ 用 `has_path` 查，**不是** `name not in rec`。
    ★ 老归档没有新字段 ⇒ 报「缺键/需 reanalyse」，**不得**自动回填（`runner.py` 里多处注释
      都是这条规矩：老归档按空处理，别拿当前配置猜当时）。
    """
    errs: list[str] = []
    for rec in records:
        task = str(rec.get("task") or "")
        cid = rec.get("case_id")
        for pred in registry.for_task(task):
            for address in pred.contract_inputs:
                if is_reply_part(address):
                    continue
                if not has_path(rec, address):
                    errs.append(f"{cid}: 缺 {address}（判据 {pred.name} 依赖它）")
        if not has_path(rec, "item_reasons"):
            errs.append(f"{cid}: 缺键 item_reasons（四态无法还原）")
    return errs


def check_archive(path: str) -> list[str]:
    """单份归档 jsonl 的 V0 ①：返回错误清单，空 = 通过。"""
    p = Path(path)
    records = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return check_archive_records(records)


def summarize_missing_keys(records: list[dict[str, Any]]) -> list[tuple[str, int, list[str]]]:
    """缺键**按种类聚合**：`(缺键描述, 行数, 前 5 条 case_id 示例)`，按描述排序。

    ★ 门禁的长期存活取决于「一屏读得完」：66 条归档刷出 96 行逐条清单会让人直接关掉输出，
      所以这里聚合成 3 类 + 计数 + 示例；逐条明细仍在 `check_archive_records` 里（真源）。
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for err in check_archive_records(records):
        cid, _sep, kind = err.partition(": ")
        groups[kind].append(cid)
    return sorted((k, len(v), v[:5]) for k, v in groups.items())


def assert_no_default_masking(pkg: str) -> list[str]:
    """AST 扫 predicates 包：判据里禁止 `.get(k, <非 None 默认>)`。

    判据必须显式区分「没有这个字段」与「有字段且值为假」，否则 V0 就形同虚设。
    ★ 扫描范围是**整个 predicates 包，零豁免名单**（§8①）：包里没有「特殊文件」，
      `registry.py` 也不是例外 —— 它原先的 `_BY_TASK.get(task, [])` 已改写成显式分支。
    """
    rel = pkg.replace(".", "/")  # evaluation.task_eval.predicates → evaluation/task_eval/predicates
    root = Path(__file__).resolve().parents[2] / rel  # parents[2] = <repo>/src
    hits: list[str] = []
    for py in sorted(root.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "get" or len(node.args) < 2:
                continue
            default = ast.unparse(node.args[1])
            if default in _MASKING_DEFAULTS:
                hits.append(f"{py.name}:{node.lineno} .get(..., {default})")
    return hits


__all__ = [
    "check_archive",
    "check_archive_records",
    "gate_rejects",
    "required_predicates",
    "summarize_missing_keys",
    "unmeasurable_required",
    "unmeasurable_tasks",
]
