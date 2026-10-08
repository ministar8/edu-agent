# Evidence Chain 实施计划（主张 ↔ 证据对齐）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让效果章每个主张的状态（已证明 / 已测量未证明 / 未测量）由机器算出，而不是由文档写出。

**Architecture:** 三层。① **Evidence Record**（`runner.CaseRecord`）扩三个状态枚举与五个 provenance 字段；
② **predicate registry**（`src/evaluation/task_eval/predicates/` 包）成为指标唯一真源，`metrics.py`/`report.py` 只读它、删本地副本；
③ **falsify + ledger** 在 record 层做 mutation 取证并导出 `evals/claims/ledger.md`。业务链只动 5.A 四项（B1/B2/B4/B7）。

**Tech Stack:** Python 3.13 + uv + Pydantic v2 + ruff/pyrefly；无 pytest（见下）。

**Spec:** `docs/EVIDENCE_CHAIN.md` v1.2（commit `738c7ce`）。本计划逐条实现其 §1~§9；两者一起读。

---

## Global Constraints

- **本仓无测试套件**（`CLAUDE.md:95`）。测试循环 = **gate 判据**：`check(label, passed, detail)` 断言 + 脚本退出码。
  新判据一律加进本计划创建的 `scripts/evidence_chain_gate.py`，并同步递增其 `_EXPECTED_ITEMS`
  （数量本身是判据，沿用 `scripts/memory_step4fix_gate.py:36,76,3397` 的既有做法）。
- **冻结件不改写**：`docs/EFFECT_PLAN.md`（§3.1/§4）、`docs/RETRIEVAL_POLICY.md`、`docs/RETRIEVAL_LAYER_DESIGN.md`。
  偏离只登记到 `docs/EXPERIMENTS.md` §20.7。
- **规模红线**：单文件 ≤600 行、单函数 ≤60 行（`CLAUDE.md:88`，人工遵守）。
- **评测器四硬规则**（`CLAUDE.md:162-171`）：① 测不到记 `None` 绝不记 `False`；② `case_invalid` 不进失败率；
  ③ `used` 需 `recalled_actual` 前提且 `correct_use` 按样本极性；④ gold 用可接受集并逐题查 `kp_index`。
- **状态词只有三个**：`已证明` / `已测量未证明` / `未测量`。文档禁止第四种措辞。
- **R3**：文档与代码注释里的计数**写成命令**，不写死数字。
- **每个 Windows 命令都带**：`PYTHONIOENCODING=utf-8 PYTHONPATH=src`。
- **零 token 纪律**：Task 1~8 不得调用 agent/judge。任何要花钱的动作只允许出现在 Task 9 的
  `retrieval_gate`（本地 TEI，不走 LLM 计费）与 §7.3 Freeze（不在本计划内）。
- **commit 规范**：中文 conventional commits，scope 用小写英文（对齐 `git log`，如 `fix(eval):`、`docs(anchor):`）。
  每步末尾 commit 前必须先跑 `uv run ruff check src/ scripts/` 与 `uv run ruff format --check src/ scripts/`。

---

## 执行纪律（v1.0 冻结，2026-10-08）

**本计划已冻结。** 每个 Task 由一个**新子代理**执行，完成即停在 checkpoint 等人审。

子代理**必须停下来报告**的情形：发现真实代码与本计划的描述不符（行号漂移、签名不同、
依赖不存在、判据计数对不上、测试无法按计划变红）。报告格式固定为四行：

```
计划说：<本 Step 原文的哪一句>
代码是：<实测 file:line + 关键片段>
影响：<哪个 Step / 哪条判据 / 哪个下游 Task>
候选：A <把计划改成 X 的最小编辑>  B <换一条实现路径>   ← 只列，不选、不做
```

**不得自行做的事**（这些都会把「按计划执行」偷偷变成「按子代理的判断执行」）：

- 扩写方案：新增判据、新增 Task、扩大 Files 清单、顺手重命名、顺手重构、顺手补测试。
- **为让判据变绿而放宽判据**——这是本计划要消灭的行为，发生在执行期同样算违规。
  判据红了就报红。只有 `check_5` 里写明的「基线本就红要先改夹具」这一条例外，且仍需报告。
- 改动 `_EXPECTED_ITEMS` 时只允许按各 Step 声明的增量变化；算不拢就停下报告，不许调数字凑绿
  （#30 的「更小的绿」正是这个）。
- 动 `docs/EVIDENCE_CHAIN.md`（冻结 spec）、任何 `EFFECT_PLAN.md` 等冻结件、或本计划的正文。
  发现 spec 也要改 ⇒ 报告，由人改。
- 执行 Task 9 Step 4（重录 6 条基线）或任何要花 token 的动作，除非该 Step 明确要求且人已在
  checkpoint 上点头。
- `git push`、打 tag、删文件、`git stash`/`checkout`/`reset`。commit 只按各 Step 写明的
  `git add <具体文件>` + `git commit` 做，禁止 `git add -A`（仓里有 41 份未跟踪结果工件与
  38MB `checkpoints.db`，一把加会污染历史）。

**允许的最小自主**：Step 内代码的**字面实现细节**（换行、变量名局部、把伪代码里标注
「实现时展开成两行」的地方写清楚），以及修自己在本 Step 内引入的语法/类型错误。
边界判据：**如果一个改动会让另一个 Task 的 Step 文本变得不准确，它就属于偏差，必须停。**

---

## 依赖矩阵（执行顺序不是线性的）

```
P−1（人工盲标，阻塞 Task 3 的可测分支）
  └─ Task 1 (record 字段/枚举) ─┬─ Task 2 (provenance + gold 出处)
                                ├─ Task 3 (registry，七个 generate 判据 + verify/memory 注册)
                                │     └─ Task 4 (report/backfill 切 registry)
                                │           └─ Task 5 (falsify) ─┐
                                │                                ├─ Task 6 (三态 + ledger)
                                │                                └─ Task 7 (V0)
                                └─ Task 8 (B7 检索失败传播 + 归因门 + memory_read_status)
                                      └─ Task 9 (B2 rerank_status + B1 语义统一 + 重录 6 条路由)
                                            └─ Task 10 (文档/工件收尾)
```

三条硬规矩，防止「先实现规则、后落地生产者」被误读成已完成：

1. **生产者先于消费者**。任何判据读取的枚举值，必须由**同一个 Task 或更早的 Task** 里的生产侧
   代码写入。因此 **B7（让 `retrieval_status == "error"` 真的可达）从 Task 9 挪进 Task 8**，
   放在归因门之前——否则 Task 8 的归因门在 B7 落地前永远看不到 `error`，
   「路由坏了」会继续伪装成「没查到」。
2. **registry 必须先能查到**。`Task 7` 的 `required_predicates(task)` 从 registry 推导，
   所以 **verify/memory 的判据注册放在 Task 3**（Task 7 之前），不能留在 Task 8——
   否则 `registry.for_task("verify")` 返回空列表 ⇒ `gate_rejects()` **静默返回 False**，
   V0 看起来全绿而实际上什么都没拦。Task 7 的 `7e` 就是专门钉这条的。
3. **允许「规则先写、闸门后验」，但必须在 Task 里写明**。本计划里唯一一处是
   Task 9 Step 3.5 的 space 方向实测：它依赖 TEI 就绪，属于机器时间；规则代码可以先合，
   但 Step 4（重录 6 条基线）**必须**排在 Step 3.5 通过之后。

---

## 前置：人工动作（不在任何 Task 内，阻塞 Task 3）

**P−1 盲标 gold**（`docs/EVIDENCE_CHAIN.md` §4.2 规程）：**约 4 人时，零 token**。

- 填 `evals/datasets/demo/generate_cases.jsonl` 对应 15 条的 `gold_answer` + `expected_difficulty`；
  填 `grade_cases.jsonl` 15 条 `human_score` 的**非两极**值（现分布 `{100.0: 8, 0.0: 7}`）。
- 标注**只读**题面 + 选项 + `knowledge/` 原始依据；**不得打开** `evals/datasets/demo/calibration_30.jsonl`
  （它含 `system_output`，与本次 case_id 重合 20 个）。
- 每条 gold 必须带出处 `gold_source_ref`（Task 2 会加字段并校验）。
- 已有基建复用，不重造：工作单 `evals/results/task_eval/GOLD_REVIEW_20261008.md`、
  翻转器 `scripts/gold_review_apply.py`（只翻确认过的 case，先试跑再 `--apply`）。

> Task 3 的 Generate 判据在 P−1 完成前只能实现到「读 gold 为 None ⇒ 输出 `missing_premise`」这一分支；
> 这是预期行为，不是缺陷，**不要**为了让测试变绿而放宽判据。

---

## Task 1: Evidence Record 扩状态枚举与 provenance

**Files:**
- Modify: `src/evaluation/task_eval/runner.py:196-322`（`CaseRecord` 字段块）
- Modify: `src/evaluation/task_eval/runner.py:281`（`retrieval_status` 取值集合）
- Create: `scripts/evidence_chain_gate.py`
- Test: `scripts/evidence_chain_gate.py`（本 Task 的判据即测试）

**Interfaces:**
- Consumes: 无（新建）
- Produces:
  - `CaseRecord.rerank_status: str`（`"" | "off" | "success" | "degraded" | "failed"`）
  - `CaseRecord.memory_read_status: str`（`"" | "not_attempted" | "success" | "empty" | "failed"`）
  - `CaseRecord.item_reasons: dict[str, str]`（字段名 → `"not_applicable" | "missing_premise" | ""`）
  - `CaseRecord.provenance: dict[str, Any]`（键：`model_refs` / `sampling` / `experiment_config_hash` /
    `dependency_lock_hash` / `argv`；**不含任何密钥原值**）
  - `scripts/evidence_chain_gate.py: check(label: str, passed: bool, detail: str = "") -> None`、
    `_EXPECTED_ITEMS: int`、`main() -> int`

- [ ] **Step 1: 先写会红的判据（新建 gate）**

创建 `scripts/evidence_chain_gate.py`：

```python
"""Evidence Chain 护栏（零 LLM）。判据数量本身也是判据。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_EXPECTED_ITEMS = 4
_ITEMS: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    _ITEMS.append((label, bool(passed), detail))


def check_1() -> None:
    """新字段必须存在，且老归档读取按「未知」处理而非猜测填充。"""
    from evaluation.task_eval.runner import CaseRecord

    rec = CaseRecord(case_id="x", task="generate", task_mode="practice", query="q")
    check("1a rerank_status 默认空串（未知）", rec.rerank_status == "")
    check("1b memory_read_status 默认空串（未知）", rec.memory_read_status == "")
    check("1c item_reasons 默认空 dict", rec.item_reasons == {})
    check("1d provenance 默认空 dict", rec.provenance == {})


def main() -> int:
    check_1()
    total = len(_ITEMS)
    for label, passed, detail in _ITEMS:
        print(f"{'PASS' if passed else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if total != _EXPECTED_ITEMS:
        print(f"判据总数 {total} ≠ 声明的 {_EXPECTED_ITEMS} —— 数量本身也是判据")
        return 1
    failed = [label for label, passed, _ in _ITEMS if not passed]
    if failed:
        print("红灯：" + ", ".join(failed))
        return 1
    print(f"全绿（{total} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 跑它，确认红在缺字段**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`
Expected: `AttributeError: 'CaseRecord' object has no attribute 'rerank_status'`

- [ ] **Step 3: 加字段（只加，不动既有字段）**

在 `runner.py` 的 `retrieval_status` 注释块之后插入：

```python
    # ★ 状态枚举取代自报布尔（EVIDENCE_CHAIN.md §5 B2/B4）。
    #   空串 = 该归档跑在写这个字段之前的代码上 = **未知**，不得按 `off`/`not_attempted` 猜。
    rerank_status: str = ""
    memory_read_status: str = ""
    # 判据项为 None 时的原因（`not_applicable` / `missing_premise`）。R5 靠它区分两种 N/A。
    item_reasons: dict[str, str] = field(default_factory=dict)
    # provenance 补齐（§3 表）：只放非密钥字段与 hash，密钥原值一律不落。
    provenance: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: 把 `retrieval_status` 的取值集合写进注释**

`runner.py:281` 那行改为带枚举说明（同一字段，值域写成注释），**沿用仓内既有值，不发明新名**：

```python
    # 值域来自 retrieval_probe（`retrieval_probe.py:66,140,149`）：
    #   `ok`（探针拿到非空 context）/ `empty`（正常查到空）/ `error`（探针抛错，已收敛不外泄）
    #   `""` = 老归档未知，不得回填。
    # ★ 刻意**不叫** `route_error`：`judge.py:373` 已经在比较 `== "error"`，改名会把这条既有
    #   判定与后续归因链同时打断。
    # ★ 实测（2026-10-08：27 份 `evals/results/task_eval/*.jsonl` / 367 条记录）：
    #   `ok`×309、`empty`×34、**`error`×0**，另有 24 条该键缺失。
    #   ⇒ `error` 目前只存在于 `retrieval_probe.py:66` 的代码默认值里，`judge.py:373` 那条分支
    #   **从未被触发过**。所以 B7 要修的不是「加一个值」，而是「让 `error` 真的可达」
    #   （BM25 把抛错咽成空结果），并且 Task 8 的归因门必须为这条分支自带取证。
    retrieval_status: str = ""
```

- [ ] **Step 5: 判据转绿 + 加「老归档不被回填」判据**

`_EXPECTED_ITEMS = 5`（`check_1()` 现有 4 项 + 下面这 1 项），`check_1()` 末尾追加：

```python
    legacy = CaseRecord(case_id="y", task="qa", task_mode="learn", query="q")
    check("1e 空 provenance 不等于「配置已核对」", "experiment_config_hash" not in legacy.provenance)
```

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`
Expected: `全绿（5 项）`

- [ ] **Step 6: 门禁与提交**

```bash
uv run ruff check src/ scripts/ && uv run ruff format --check src/ scripts/ && uv run pyrefly check
git add src/evaluation/task_eval/runner.py scripts/evidence_chain_gate.py
git commit -m "feat(eval): Evidence Record 扩三状态枚举 + provenance 槽位（EVIDENCE_CHAIN Task 1）"
```

---

## Task 2: provenance 落盘 + gold 出处字段

**Files:**
- Modify: `src/evaluation/task_eval/runner.py`（`run_case` 里 `record.code_version = ...` 附近）
- Modify: `src/evaluation/task_eval/cases.py:226-296`（`Gold`）、`:72-91`（`GOLD_FIELDS`）
- Modify: `src/evaluation/task_eval/gold_sanity.py`
- Test: `scripts/evidence_chain_gate.py`

**Interfaces:**
- Consumes: `Task 1` 的 `CaseRecord.provenance`
- Produces:
  - `runner.build_provenance(argv: list[str]) -> dict[str, Any]`
  - `Gold.gold_source_ref: dict[str, str]`（键为被 gold 支撑的字段名，值为 `knowledge/` 下的相对路径或 `kp:<id>`）

- [ ] **Step 1: 写红的判据**

```python
def check_2() -> None:
    """provenance 必须能区分「没记」与「记了且不同」；gold 必须有出处。"""
    import json
    import tempfile
    from pathlib import Path as P

    from evaluation.task_eval.runner import build_provenance

    prov = build_provenance(["run", "--task", "generate"])
    check("2a argv 落盘", prov.get("argv") == ["run", "--task", "generate"])
    check("2b 含 experiment_config_hash", isinstance(prov.get("experiment_config_hash"), str))
    check("2c 含 dependency_lock_hash", isinstance(prov.get("dependency_lock_hash"), str))
    check("2d 不落任何密钥原值", "api_key" not in json.dumps(prov).lower())

    from evaluation.task_eval.cases import Gold

    check("2e Gold 有 gold_source_ref 字段", "gold_source_ref" in Gold.__dataclass_fields__)
```

`_EXPECTED_ITEMS = 10`（Task 1 结束时为 5，本步 +5），`main()` 里在 `check_1()` 后调 `check_2()`。

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`
Expected: `ImportError: cannot import name 'build_provenance'`

- [ ] **Step 2: 实现 `build_provenance`**

`runner.py` 新增（放在 `preflight_check` 之后，避免 `CaseRecord` 之前引用）：

```python
# ★ 全部是 settings.py 里**真实存在**的字段名（`RERANK_MODE` 不存在，别写进白名单 ——
#   白名单里一个不存在的键会静默变成 None，config_hash 就永远测不出它变了）。
_PROVENANCE_CONFIG_KEYS: tuple[str, ...] = (
    "DEFAULT_MODEL",
    "LLM_MODEL",
    "RAGAS_JUDGE_MODEL",
    "TEMP_PRECISE",
    "TEMP_CREATIVE",
    "TEMP_DEFAULT",
    "RETRIEVAL_SCORE_THRESHOLD",
    "RERANK_ENABLED",
    "USE_FAKE_EMBEDDING",
    "SEMANTIC_CACHE_ENABLED",
    "MEMORY_WEAK_MIN_HITS",
    "MEMORY_WEAK_WINDOW_DAYS",
)


def build_provenance(argv: list[str]) -> dict[str, Any]:
    """结果 ↔ 配置的那一跳（EVIDENCE_CHAIN.md §3）。

    ★ 只导出白名单里的**行为开关**，其余配置压成 hash —— 直接落 `settings` 会把密钥
      带进归档（#29 修过的同一类泄漏，这次由结构挡住而不是靠自觉）。
    """
    import hashlib
    import json

    from core.settings import settings

    cfg = {k: getattr(settings, k, None) for k in _PROVENANCE_CONFIG_KEYS}
    lock = Path("uv.lock")
    return {
        "model_refs": {
            "agent": str(settings.DEFAULT_MODEL),
            "rag_chain": str(settings.LLM_MODEL),
            # judge 走 `settings.ragas_judge_model`（= RAGAS_JUDGE_MODEL or LLM_MODEL，:378）
            # —— judge 用比生成模型更强的模型是为了避免自评偏差，所以它换了就等于换了尺子
            "judge": str(settings.ragas_judge_model),
        },
        "sampling": {
            "temp_precise": settings.TEMP_PRECISE,  # 批改
            "temp_creative": settings.TEMP_CREATIVE,  # 出题
            "temp_default": settings.TEMP_DEFAULT,  # 讲解 / supervisor / 检索链
        },
        "experiment_config_hash": hashlib.sha256(
            json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:12],
        "dependency_lock_hash": (
            hashlib.sha256(lock.read_bytes()).hexdigest()[:12] if lock.exists() else ""
        ),
        "argv": list(argv),
    }
```

并在 `run_case` 里已有的 `record.code_version = ...` 同处补：

```python
    record.provenance = build_provenance(list(sys.argv[1:]))
```

- [ ] **Step 3: `Gold` 加出处字段并进 `GOLD_FIELDS`**

```python
    # gold 的**外部出处**（EVIDENCE_CHAIN.md §4.2 盲标规程第 2 条）：
    #   键 = 被支撑的字段名（gold_answer / expected_difficulty / human_score），
    #   值 = `knowledge/` 相对路径或 `kp:<id>`。无出处视为未填 ⇒ missing_premise。
    gold_source_ref: dict[str, str] = field(default_factory=dict)
```

`GOLD_FIELDS["generate"]` 追加 `"gold_source_ref"`；`parse_case()` 里按现有 `_as_*` 风格加一条
`_as_str_dict(raw_gold.get("gold_source_ref"))`（若该 helper 不存在则在 `cases.py:343-388` 区间新增，
照 `_as_str_list` 的写法：非法值返回 `{}` 不抛错）。

- [ ] **Step 4: sanity 出 ERROR 级检查（有 gold 值但无出处）**

`gold_sanity.py` 的错误收集处新增一条（沿用现有 `ERROR`/`WARN` 列表写法）：

```python
        for field_name in ("gold_answer", "expected_difficulty", "human_score"):
            if getattr(case.gold, field_name, None) is not None and not (
                case.gold.gold_source_ref or {}
            ).get(field_name):
                errors.append(f"{case.case_id}: {field_name} 有值但无 gold_source_ref")
```

- [ ] **Step 5: 转绿并复跑现有 sanity（零 LLM）**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -m evaluation.task_eval sanity
```
Expected: `全绿（10 项）`；sanity 对现有 66 条**不得新增 ERROR**（现有一切 gold 都没出处，
所以该检查在未填 gold 上应为 0 命中 —— 若报出 66 条 ERROR，说明 Step 4 把「无 gold 值」也算错了）。

- [ ] **Step 6: 提交**

```bash
git add src/evaluation/task_eval/runner.py src/evaluation/task_eval/cases.py src/evaluation/task_eval/gold_sanity.py scripts/evidence_chain_gate.py
git commit -m "feat(eval): provenance 五项落盘 + gold 出处字段（密钥白名单隔离）"
```

---

## Task 3: predicate registry 与四态（`predicates/` 包）

**Files:**
- Create: `src/evaluation/task_eval/predicates/__init__.py`
- Create: `src/evaluation/task_eval/predicates/registry.py`
- Create: `src/evaluation/task_eval/predicates/common.py`
- Create: `src/evaluation/task_eval/predicates/generate.py`
- Create: `src/evaluation/task_eval/predicates/verify.py`、`src/evaluation/task_eval/predicates/memory.py`
- Modify: `src/evaluation/task_eval/metrics.py:387-415`（加 6 个结构 helper，紧邻 `structure_completeness`）
- Test: `scripts/evidence_chain_gate.py`

**Interfaces:**
- Consumes: `Task 1.item_reasons`、`Task 2.Gold.gold_source_ref`
- Produces:
  - `Verdict` 常量集 `PREDICATE_VERDICTS = ("pass", "fail", "not_applicable", "missing_premise")`
  - `Predicate` dataclass：`name / tier / contract_ref / contract_inputs / required_when / fn / falsifier`
  - `registry.get(name: str) -> Predicate`、`registry.for_task(task: str) -> list[Predicate]`
  - `common.to_record_value(v: Verdict) -> bool | None`、`common.rate(verdicts) -> dict[str, int | float | None]`
    （返回多两个键：`n_a_not_applicable` / `n_a_missing_premise`）
  - `common.composite(name: str, verdicts: dict[str, Verdict]) -> Verdict`

- [ ] **Step 1: 写红的判据（含 R5 事故回归）**

```python
def check_3() -> None:
    """R5：应有但测不到 ⇒ 毒化合取。「不适用」⇒ 不毒化。"""
    from evaluation.task_eval.predicates import common as pc

    mix = {"gen_structure": "pass", "gen_coverage": "pass"}
    check("3a 全 pass ⇒ pass", pc.composite(mix) == "pass")
    check("3b 任一 fail ⇒ fail", pc.composite({**mix, "gen_correctness": "fail"}) == "fail")
    check(
        "3c required 项 missing_premise ⇒ 复合 missing_premise（★ 不得为 pass）",
        pc.composite(
            {**mix, "gen_correctness": "missing_premise", "gen_answerability": "missing_premise"}
        )
        == "missing_premise",
    )
    check(
        "3d not_applicable 不毒化",
        pc.composite({**mix, "gen_difficulty": "not_applicable"}) == "pass",
    )
    r = pc.rate(["pass", "fail", "missing_premise", "not_applicable"])
    check("3e 分母只含已测", r["n"] == 2, str(r))
    check("3f 两种 N/A 分开计数", r["n_a_missing_premise"] == 1 and r["n_a_not_applicable"] == 1)
    check(
        "3g 全 missing_premise ⇒ rate=None 而非 0.0",
        pc.rate(["missing_premise", "missing_premise"])["rate"] is None,
    )
```

`_EXPECTED_ITEMS = 17`（Task 2 结束时为 10，本步 +7）。
Run 预期：`ModuleNotFoundError: evaluation.task_eval.predicates`。

- [ ] **Step 2: `common.py` 实现四态与 R5**

```python
"""四态判据与复合语义（EVIDENCE_CHAIN.md §1.3/§1.6）。"""

from __future__ import annotations

from typing import Literal

Verdict = Literal["pass", "fail", "not_applicable", "missing_premise"]
PREDICATE_VERDICTS: tuple[Verdict, ...] = ("pass", "fail", "not_applicable", "missing_premise")
_MEASURED: frozenset[Verdict] = frozenset({"pass", "fail"})


def to_record_value(verdict: Verdict) -> bool | None:
    """落盘仍是三态布尔；`item_reasons` 另存原因。二者合起来才无损（§1.3 四态）。"""
    return {"pass": True, "fail": False}.get(verdict)


def from_record_value(value: object, reason: str) -> Verdict:
    """从归档还原四态：True/False 直接映射，None 时**必须**看 reason。

    ★ reason 缺失或非法 ⇒ 按 `missing_premise` 处理（保守侧）：老归档的 `None` 无法证明
      当时是「不适用」还是「测不到」，而把它当「不适用」正是 §4.2 事故的形状。
    """
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "not_applicable" if reason == "not_applicable" else "missing_premise"


def composite(
    verdicts: dict[str, Verdict],
    *,
    optional: frozenset[str] = frozenset(),
) -> Verdict:
    """合取复合。`optional`（契约不要求的项）连 missing_premise 都不毒化。

    ★ 规则表见 §1.6：fail 优先 → 再 missing_premise → 有一个 pass 即 pass →
      什么都没测成 ⇒ missing_premise。`not_applicable` 有权缺席。
    """
    judged = {k: v for k, v in verdicts.items() if k not in optional}
    if not judged:
        return "not_applicable"
    if "fail" in judged.values():
        return "fail"
    if "missing_premise" in judged.values():
        return "missing_premise"
    return "pass" if "pass" in judged.values() else "not_applicable"


def rate(verdicts: list[Verdict]) -> dict[str, object]:
    measured = [v for v in verdicts if v in _MEASURED]
    return {
        "rate": (sum(1 for v in measured if v == "pass") / len(measured)) if measured else None,
        "n": len(measured),
        "n_a_missing_premise": sum(1 for v in verdicts if v == "missing_premise"),
        "n_a_not_applicable": sum(1 for v in verdicts if v == "not_applicable"),
    }


def is_reply_part(address: str) -> bool:
    """`reply#stem` 这类地址指向 reply 文本内部的语义片段。

    ★ 它**不是** record 的键，所以 V0 的键存在性检查必须跳过它 —— 它由 Task 5 的
      R1-A 覆盖检查负责。两边共用这一套地址语法，但各管各的那一类。
    """
    return address.startswith("reply#")


def has_path(rec: object, dotted: str) -> bool:
    """点分路径的**键存在性**检查。`top_items[].knowledge_points` = 逐元素，任一可达即存在。"""
    parts = dotted.split(".")
    cur = rec
    for i, part in enumerate(parts):
        if part.endswith("[]"):
            if not isinstance(cur, list):
                return False
            head = part[:-2]  # `x[].y` 里 head=x 已在上一层取到，这里通常为 ""
            target = cur if not head else [getattr(item, head, None) for item in cur]
            tail = parts[i + 1 :]
            if not tail:
                return bool(target)
            return any(has_path(item, ".".join(tail)) for item in target)
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def drop_path(rec: dict, dotted: str) -> None:
    """按点分路径删键（falsify 的 `drop_path` op 用）。路径不存在时静默返回。"""
    parts = dotted.split(".")
    cur = rec
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
```

`has_path` / `drop_path` / `is_reply_part` 是**路径语法的唯一实现处**：Task 5 的取证与 Task 7 的
V0 都从这里取，两边不可能再说两种地址语言（这正是 P1-6 要消灭的分叉）。

- [ ] **Step 3: `registry.py` + `generate.py` 的五个判据**

```python
# registry.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from evaluation.task_eval.predicates.common import Verdict


@dataclass(frozen=True)
class Predicate:
    name: str
    task: str
    tier: int
    contract_ref: str
    contract_inputs: tuple[str, ...]
    required_when: Callable[[Any], bool]
    fn: Callable[[Any], Verdict]
    falsifier: str
    optional: bool = False


_BY_NAME: dict[str, Predicate] = {}
_BY_TASK: dict[str, list[Predicate]] = {}


def register(pred: Predicate) -> None:
    if pred.name in _BY_NAME:
        raise ValueError(f"判据重复注册：{pred.name}（一个指标只允许一处定义）")
    _BY_NAME[pred.name] = pred
    _BY_TASK.setdefault(pred.task, []).append(pred)


def get(name: str) -> Predicate:
    return _BY_NAME[name]


def for_task(task: str) -> list[Predicate]:
    return _BY_TASK.get(task, [])
```

★ registry **不提供** `composite_name()` 之类的「复合指标叫什么」查询：复合名由调用方按任务
自己传（`report.py` 里就是 `pc.composite(...)`），多一个查询函数就多一处可能漂移的间接层。

`generate.py` 的判据要用到 **`metrics.py` 里今天还不存在的六个 helper**，先加 helper
（放在 `metrics.py:387` 的 `structure_completeness` 旁边，复用同一批 `_STRUCTURE_*` 常量，
**不要再写一份正则** —— 那是第二套真源）。第四个是
`difficulty_of(reply) -> str | None`（从生成题正文里抽「难度：适中/basic/…」）；
★ 抽不出来时判据返回 `missing_premise` 而**不是** `fail` —— 解析器的失败不能记成产品的失败。
第五个是 `strip_reply_part(reply, part) -> str`、第六个是 `rewrite_reply_part(reply, part, new_text)`：
**Task 5 的夹具唯一允许的两种破坏手段**，分段知识留在 metrics（结构真源），falsify 只调用不复制正则。

```python
_ANSWER_LINE = re.compile(r"(?:标准答案|参考答案|答案)\s*[：:]\s*([^\n。；;]{0,40})", re.I)
_LETTER = re.compile(r"([A-D])")
_OPTION_LINE = re.compile(r"^\s*([A-D])\s*[.、．)）]\s*\S", re.M)
_ANALYSIS_KEY = re.compile(r"(?:所以|因此|故|答案[是为]?|正确)[^\n。]{0,12}?选?\s*([A-D])\b", re.I)


def option_letters(reply: str) -> list[str]:
    """选项**集合**（去重保序）。这里去重是对的：选项集本来就该是集合。"""
    seen: list[str] = []
    for m in _OPTION_LINE.finditer(str(reply or "")):
        k = m.group(1).upper()
        if k not in seen:
            seen.append(k)
    return seen


def answer_keys_of(reply: str) -> list[str]:
    """答案键序列 —— ★ **不去重、不取第一个**。

    数量本身就是判据：`标准答案：A、B` ⇒ `['A','B']` ⇒ 单选语义下不唯一 ⇒ fail。
    如果这里返回单个键（旧写法 `answer_key_of()`），「两个都算对」这个失败形状
    在读数阶段就被抹掉了，`gen_answer_key_validity` 只剩「键 ∈ 选项」半条契约。
    """
    m = _ANSWER_LINE.search(str(reply or ""))
    return [k.upper() for k in _LETTER.findall(m.group(1))] if m else []


def analysis_key_of(reply: str) -> str | None:
    """解析正文最后落到的那个选项（#33 产品规则「答案键与解析同结论」的评测化）。"""
    keys = [k.upper() for k in _ANALYSIS_KEY.findall(str(reply or ""))]
    return keys[-1] if keys else None


_DIFFICULTY_LINE = re.compile(
    r"(?:难度|难易程度)\s*[：:]\s*(基本|基础|简单|中等|适中|较难|困难|basic|easy|medium|hard)",
    re.I,
)


def difficulty_of(reply: str) -> str | None:
    """从生成题正文里抽难度档（`gen_difficulty` 的实际侧输入）。

    ★ 抽不出来 ⇒ 判据返回 `missing_premise` 而**不是** `fail`：解析器的失败不能记成产品的失败。
      `metrics._as_difficulty()`（:664）已负责把中文档名映射到 1–5，这里只做抽取，不重复映射。
    """
    m = _DIFFICULTY_LINE.search(str(reply or ""))
    return m.group(1) if m else None


# ★ 分段名与 `structure_completeness` 用的是**同一批** `_STRUCTURE_*` 常量（metrics.py:391-394）
_REPLY_PART_PATTERNS: dict[str, re.Pattern[str]] = {
    "stem": _STRUCTURE_STEM,
    "options_or_task": _STRUCTURE_OPTIONS,
    "answer": _STRUCTURE_ANSWER,
    "explanation": _STRUCTURE_EXPLAIN,
}


def strip_reply_part(reply: str, part: str) -> str:
    """删掉 reply 里某个语义片段的标识（Task 5 `omit_reply_part` 的唯一实现处）。

    「判据认为某段存在」与「夹具把那段抹掉」必须说同一种语言，否则会出现
    夹具删 A 段、判据读 B 段 的假红/假绿。未知片段名直接抛错，不静默返回原文。
    """
    pattern = _REPLY_PART_PATTERNS.get(part)
    if pattern is None:
        raise ValueError(f"未知的 reply 片段名：{part}")
    return pattern.sub("", str(reply or ""))


def rewrite_reply_part(reply: str, part: str, new_text: str) -> str:
    """把某个片段换成给定文本（Task 5 的 `dual_answer` / `flip_conclusion` 用）。

    ★ 与 `strip_reply_part` 共用 `_REPLY_PART_PATTERNS`：分段知识仍然只有 metrics 一份，
      falsify 只声明「换哪一段成什么」，不认识正则。
    """
    pattern = _REPLY_PART_PATTERNS.get(part)
    if pattern is None:
        raise ValueError(f"未知的 reply 片段名：{part}")
    return pattern.sub(new_text, str(reply or ""), count=1)
```

★ 这两个正则是**待标定起点**，不是定稿：Step 3 末尾要在 15 条 `reply` 上打印分布，
逐条核对「抽取到的键」与「人读到的键」是否一致，再把偏差写进 gate 判据。
不这么做就等于用一个没验过的解析器去证明另一个判据。

```python
# generate.py —— 关键在两个**改名**（§4.1：证据不是等价定义就不沿用原名）
from evaluation.task_eval import metrics
from evaluation.task_eval.predicates.common import Verdict
from evaluation.task_eval.predicates.registry import Predicate, register

# 真实键名来自 metrics.structure_completeness 的返回（stem/options_or_task/answer/explanation）
_GEN_KEYS = ("stem", "options_or_task", "answer", "explanation")


def _structure(rec: dict) -> Verdict:
    """§3.1 completeness_pass：四件套**逐一非空**，不是「整条能解析」。"""
    parsed = metrics.structure_completeness(str(rec.get("reply") or ""))
    return "fail" if [k for k in _GEN_KEYS if not parsed.get(k)] else "pass"


def _answer_key_validity(rec: dict) -> Verdict:
    """原 `gen_answerability` 的**必要非充分**机械替身。它不证明这题可被作答判定。

    契约是三条，缺一条就不算覆盖（spec §6 那行的「two correct options」是第 2 条）：
      ① 答案键可解析  ② 键数**恰好为 1**  ③ 该键 ∈ 选项集
    """
    reply = str(rec.get("reply") or "")
    opts = metrics.option_letters(reply)
    if not opts:
        return "missing_premise"  # 连选项集都读不出来 = 没资格谈唯一性
    keys = metrics.answer_keys_of(reply)
    if len(keys) != 1:
        return "fail"  # 0 个键（没给答案）与多键（A、B 都算对）在这里都是失败
    return "pass" if keys[0] in opts else "fail"


def _analysis_agreement(rec: dict) -> Verdict:
    """原 `gen_correctness` 的**必要非充分**机械替身（#33 产品规则的评测化）。
    ★ 它不证明答案对不对 —— #36 手验 5 道里 2 道客观错、1 道满分漏检就是这件事的证据。"""
    reply = str(rec.get("reply") or "")
    keys, cited = metrics.answer_keys_of(reply), metrics.analysis_key_of(reply)
    if cited is None or len(keys) != 1:
        return "missing_premise"  # 点不出可比的「键 ↔ 解析结论」= 测不到，不是不合格
    return "pass" if keys[0] == cited else "fail"


def _correctness(rec: dict) -> Verdict:
    """§3.1 冻结原文是「gold 判定正确」⇒ 需要外部 gold，且必须带出处（盲标规程）。"""
    gold = rec.get("gold") or {}
    if not gold.get("gold_answer") or not (gold.get("gold_source_ref") or {}).get("gold_answer"):
        return "missing_premise"
    keys = metrics.answer_keys_of(str(rec.get("reply") or ""))
    return "pass" if len(keys) == 1 and keys[0] == str(gold["gold_answer"]).strip().upper() else "fail"
```

★ **本 Task 注册的判据名是 7 个，不是 5 个**，两类不能混：

| 名字 | 来源 | 无 gold 时 |
|---|---|---|
| `gen_structure` / `gen_coverage` / `gen_difficulty` | §3.1 冻结五项 | 可测（coverage/difficulty 按 `required_when` 决定是否缺席） |
| `gen_correctness` / `gen_answerability` | §3.1 冻结五项，**要外部 gold** | `missing_premise`（名字保留、状态诚实） |
| `gen_answer_key_validity` / `gen_analysis_agreement` | 本轮新增的机械替身，**必要非充分** | 可测，但**永远不顶替**上面两个名字进门槛行 |

`Task 7` 的 required 集合**从 registry 推导**（见那里），因此这份名单只在此处定义一次；
将来再改名不会再出现「V0 查一个不存在的判据名」。

**同一 Task 还要注册 verify/memory 的判据**（Task 7 的 `required_predicates()` 依赖它们已在册）。
两个文件都是薄包装，公式仍只在 `metrics.py` 一处：

```python
# verify.py —— D14 的三条行为层判据，全部是既有 metrics 函数的 verdict 化
def _fabricated(rec: dict) -> Verdict:
    if rec.get("reply") is None or rec.get("retrieval_status") == "":
        return "missing_premise"  # 探针跑/无回复：没测，不是「没编题」
    return "fail" if metrics.verify_fabricated(str(rec["reply"])) else "pass"


# memory.py —— 唯一公式仍在 metrics.memory_correct_use_from_record，这里只翻成 verdict
def _correct_use(rec: dict) -> Verdict:
    v = metrics.memory_correct_use_from_record(rec)
    if v is None:
        return "missing_premise" if rec.get("memory_read_status") in (
            "failed", "not_attempted", ""
        ) else "not_applicable"
    return "pass" if v else "fail"
```

★ `ver_fabricated` 是 §6 的**硬条件**（必须 0），所以它 `required`；
`memory_correct_use` 的 `None` 必须能分辨「读链坏了 / 没尝试读」与「样本不适用」——
这正是 Task 1 那个 `memory_read_status` 与 Task 8 归因门要供的料。qa/grade 的判据本轮不强制注册
（它们的门槛行是 `final_quality` 与 `score_tolerance`，由 `metrics.rate` 直接算，无合取风险）；
若将来要进 registry，`for_task` 加两项即可，**不要**提前铺。

`register()` 把这**七个**判据全部登记；`gen_coverage` 包一层 `metrics.kp_coverage`（`expected_kp`
为空 ⇒ `not_applicable`）、`gen_difficulty` = `metrics.difficulty_match(gold.expected_difficulty,
metrics.difficulty_of(reply))`，并加两条前置：`gold.expected_difficulty` 缺失或 `difficulty_of()`
抽不出来 ⇒ `missing_premise`；query 未指定难度 ⇒ `optional=True`（见 §1.6 族级零覆盖披露）。
★ 旧 `cli.py:306-307` 的 backfill 把 actual 侧**永远写成 `None`**，所以 `gen_difficulty` 才会
15/15 全 N/A —— 那不是「难度不适用」，是「一侧输入从来没被读过」。这条现在由 `required_when`
与 `has_path` 双双拦住。

`contract_inputs` 一律用**点分路径 / `reply#片段` 两种写法之一**（Task 7 的 V0 与 Task 5 的取证
共用这套地址语法，见「contract_input 路径语法」一节）：

| 判据 | `contract_inputs` |
|---|---|
| `gen_structure` | `("reply#stem", "reply#options_or_task", "reply#answer", "reply#explanation")` |
| `gen_answer_key_validity` | `("reply#answer", "reply#options_or_task")` |
| `gen_analysis_agreement` | `("reply#answer", "reply#explanation")` |
| `gen_correctness` | `("reply#answer", "gold.gold_answer", "gold.gold_source_ref.gold_answer")` |
| `gen_coverage` | `("top_items[].knowledge_points", "gold.expected_kp")` |
| `gen_difficulty` | `("gold.expected_difficulty", "reply#difficulty")` |
| `gen_answerability` | `("gold.gold_answer", "gold.gold_source_ref.gold_answer")`（人工判定为主 ⇒ 无 gold 即 `missing_premise`） |
`contract_ref` 一律写 `EFFECT_PLAN.md §3.1 <对应项名>`，`contract_inputs` 写真实字段名。

★ Step 3 收尾必做一次标定：把 15 条 `reply` 的 `answer_keys_of` / `analysis_key_of` /
`option_letters` / `difficulty_of` 四者打印成表逐条人读核对，偏差写进 `evidence_chain_gate.py`
的新判据（Run：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -c` 一段临时读取，**不要**把
这段核对脚本提交进仓 —— 它是标定过程，不是判据）。

- [ ] **Step 4: 判据转绿**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`
Expected: `全绿（16 项）`

- [ ] **Step 5: 找到旧合取的全部调用点（不许凭记忆）**

```bash
grep -rn "every_item_passes\|gen_case_pass\|delivery_rate" src scripts | tee /tmp/ec_callsites.txt
```
Expected: 至少命中 `report.py:157`、`report.py:160-162`、`cli.py`（backfill）、
`scripts/memory_step4fix_gate.py` 里断言它的项。逐处记下，Task 4 一并切换。

- [ ] **Step 6: 提交**

```bash
git add src/evaluation/task_eval/predicates/ scripts/evidence_chain_gate.py
git commit -m "feat(eval): predicate registry + 四态 + R5 复合语义（correctness/answerability 改名）"
```

---

## Task 4: `report.py`/`cli.py` 切到 registry 并删本地副本

**Files:**
- Modify: `src/evaluation/task_eval/report.py:144-162`
- Modify: `src/evaluation/task_eval/cli.py:282-322`（`_backfill`）
- Modify: `src/evaluation/task_eval/judge.py:265-279`（`_sync_generate_correctness`）
- Modify: `src/evaluation/task_eval/metrics.py:432-443`
- Test: `scripts/evidence_chain_gate.py`

**Interfaces:**
- Consumes: `Task 3` 的 `predicates.for_task/get`、`common.rate/composite`
- Produces:
  - `report.TaskReport.gen_items: dict[str, dict]`（值从百分数变成 `rate()` 的 dict —— 字段名不变，形状变）
  - `report.TaskReport.gen_case_pass: dict`（同上）
  - `cli._backfill` 重算**所有**任务的 registry 判据（不止 generate）

- [ ] **Step 1: 写红的判据**

```python
def check_4() -> None:
    """报告必须只从 registry 取数；旧 `every_item_passes` 不得再被生产代码引用。"""
    import ast
    import pathlib

    from evaluation.task_eval.report import summarize_task

    recs = [
        {
            "task": "generate",
            "case_id": "g1",
            "reply": "",
            "gold": {},
            "item_reasons": {},
        }
    ]
    rep = summarize_task("generate", recs)
    check("4a gen_case_pass 变 missing_premise 而非 1.000（§4.2 回归）",
          isinstance(rep.gen_case_pass, dict) and rep.gen_case_pass.get("rate") is None)
    check("4b 报告里带出 missing_n", isinstance(rep.gen_case_pass.get("n_a_missing_premise"), int))

    banned = ("every_item_passes",)
    hits = []
    for py in pathlib.Path("src").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned:
                hits.append(f"{py}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in banned:
                hits.append(f"{py}:{node.lineno}")
    check("4c 生产代码不再引用旧合取函数", not hits, "; ".join(hits))
```

`_EXPECTED_ITEMS = 20`（Task 3 结束时为 17，本步只 +3：4a/4b/4c。★ **4d 要到 Step 5 才出现**，
那时才把声明值改成 21 —— 提前写 21 会让严格按 checkbox 执行的 agent 在 Step 1 就撞上计数矛盾）。
Run 预期 4a 先红（现在 `summarize_task` 返回的是百分数而非 `rate()` dict）。

- [ ] **Step 2: `summarize_task` 的 generate 块改为驱动 registry**

```python
    if task == "generate":
        from evaluation.task_eval.predicates import common as pc
        from evaluation.task_eval.predicates import registry

        preds = registry.for_task("generate")
        verdicts_per_case: list[dict[str, str]] = []
        for r in records:
            per = {}
            for p in preds:
                v = p.fn(r)
                r[p.name] = pc.to_record_value(v)
                r.setdefault("item_reasons", {})[p.name] = (
                    "" if v in pc.PREDICATE_VERDICTS[:2] else v
                )
                per[p.name] = v
            verdicts_per_case.append(per)
        rep.gen_items = {p.name: pc.rate([v[p.name] for v in verdicts_per_case]) for p in preds}
        optional = frozenset(p.name for p in preds if p.optional)
        comp = [pc.composite(v, optional=optional) for v in verdicts_per_case]
        rep.gen_case_pass = pc.rate(comp)
```

（原 `item_keys` 五元组字面量与 `metrics.delivery_rate` 调用整段删除；`rep.gen_delivery`
若仍被 `render_markdown` 引用则同样接 `pc.rate()`，不留旧路径。）

- [ ] **Step 3: 删 `metrics.every_item_passes` 与 `delivery_rate`，连带删断言它们的 gate 项**

```bash
# 先确认 /tmp/ec_callsites.txt（Task 3 Step 5）里剩下的只有定义与 gate
grep -n "every_item_passes\|delivery_rate" /tmp/ec_callsites.txt
```
删除 `metrics.py:418-443` 两个函数。`scripts/memory_step4fix_gate.py` 里引用它们的判据
**改成引用 registry 的复合**（不是删掉判据 —— 删了会让护栏计数变小，那是 #30 明确禁止的
「更小的绿」），并同步该脚本的 `_EXPECTED_ITEMS`（数量不变则不动）。

- [ ] **Step 4: `_backfill` 改为按 registry 重算所有任务**

```python
    from evaluation.task_eval.predicates import common as pc
    from evaluation.task_eval.predicates import registry

    for rec in records:
        task = str(rec.get("task") or "")
        for pred in registry.for_task(task):
            v = pred.fn(rec)
            rec[pred.name] = pc.to_record_value(v)
            rec.setdefault("item_reasons", {})[pred.name] = "" if v in ("pass", "fail") else v
```

删除原先五段硬编码赋值（`cli.py:301-308`）。
`judge._sync_generate_correctness`（`judge.py:265-279`）改为调用 `registry.get("gen_correctness").fn(record)`
后写回 —— **「谁写 final_quality，谁负责刷新依赖它的派生指标」这条归属规则保留**，
只是实现从本地公式换成 registry 定义。

- [ ] **Step 5: 修 `reprobe` 的 provenance 脱钩（§3 那条「旧输入新输出」）**

`cli.py:260-279` 的 `_update_retrieval_fields` 用**当前**检索覆盖 `kp_hit`/`category_hit`/`exam_hit`，
却把 `retrieval_cfg`、`top_items`、`code_version`、`prompt_set_version` 留在旧值上；
同一函数还把 `k` 硬编码成 5（`cli.py:266`），无视 `--k`。改法（规则：**覆盖指标必须同写 provenance，
否则拒绝写入**）：

```python
def _update_retrieval_fields(rec: dict, case, probe, *, k: int, cfg: dict) -> None:
    """只重算检索侧指标；provenance 必须与新的读数同源，否则归档会自相矛盾。"""
    rec["kp_hit"] = ...          # 沿用现有三行赋值，但 k 来自参数，不再硬编码 5
    rec["category_hit"] = ...
    rec["exam_hit"] = ...
    rec["reprobe_of"] = str(rec.get("code_version") or "")   # 记下被覆盖前的读数归属
    rec["retrieval_cfg"] = dict(cfg)
    rec["code_version"] = _current_code_version()
    rec["prompt_set_version"] = PROMPT_SET_VERSION
```

并在 `_reprobe` 里把 `k=args.k` 与 `cfg` 传进来；`_update_retrieval_fields` 的调用点见
`grep -n "_update_retrieval_fields" src/evaluation/task_eval/cli.py`。
判据加进 `check_4`，并把声明值改成 `_EXPECTED_ITEMS = 21`（20 + 4d）：

```python
    import inspect

    from evaluation.task_eval import cli

    sig = inspect.signature(cli._update_retrieval_fields)
    check("4d reprobe 必须显式接 k 与 cfg（不再硬编码 5）",
          {"k", "cfg"} <= set(sig.parameters))
```

- [ ] **Step 6: 零 token 重算 ④/⑤ 两份归档，核对 §4.2 的预期**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -m evaluation.task_eval backfill \
  --records evals/results/task_eval/phase1_final_gate_20261008.jsonl \
  --out evals/results/task_eval/ec_r1_final_gate.jsonl
```
Expected: Generate 块打印 `gen_case_pass` 的 `rate=None`、`n=0`、`n_a_missing_premise=15`
⇒ **正是 §4.2 说的「0.867 与 0.733 一起失效」**。确认 `structure`/`coverage` 单项率仍在（`n>0`）。
★ 本步不得覆写原文件（`--out` 指向新名），原归档留待 Task 10 标 `superseded`。

- [ ] **Step 7: 提交**

```bash
uv run ruff check src/ scripts/ && uv run pyrefly check
git add -A src/evaluation/task_eval scripts/evidence_chain_gate.py evals/results/task_eval/ec_r1_final_gate.jsonl
git commit -m "refactor(eval): report/backfill 驱动 registry，删 every_item_passes/delivery_rate 副本"
```

---

## Task 5: falsify —— mutation 覆盖 `contract_inputs`

**Files:**
- Create: `src/evaluation/task_eval/falsify.py`
- Modify: `scripts/evidence_chain_gate.py`（`check_5` + 夹具 + `--emit`）
- Test: `scripts/evidence_chain_gate.py`

**Interfaces:**
- Consumes: `Task 3` 的 `Predicate.fn / contract_inputs / for_task`
- Produces: `falsify.declared_mutations(pred) -> list[dict]`、
  `falsify.apply(mutation=..., record=...) -> dict`、
  `falsify.evaluate(pred, base_rec, broken_rec, *, mutation_input, siblings=None) -> FalsifyResult`、
  `falsify.FalsifyResult`（`predicate / input / baseline / flipped / collateral / raised`）、
  `falsify.coverage(preds, covered) -> dict[str, tuple[str, ...]]`（返回**缺失**的输入名）、
  `predicates.common.has_path(rec, dotted) -> bool` 与 `drop_path(rec, dotted) -> None`
  （★ Task 7 的 V0 复用同一对函数 —— 路径语法只允许有一份）、
  `evals/claims/falsify_latest.json`（Task 6 的 `falsify_passed` 输入）

- [ ] **Step 1: 写红的判据（R1-A 的形状，含「只删一个字段」的反例）**

```python
def check_5() -> None:
    from evaluation.task_eval import falsify
    from evaluation.task_eval.predicates import registry

    base = {
        "task": "generate",
        "case_id": "g1",
        "reply": _gen_reply(),
        "gold": {"gold_answer": "B", "gold_source_ref": {"gold_answer": "kp:co.overview"}},
        "item_reasons": {},
    }
    p = registry.get("gen_structure")
    siblings = {q.name: (q, base) for q in registry.for_task("generate") if q.name != p.name}
    # ★ 被破坏的是哪个契约输入，由 **mutation 声明**给出，不从两条 record 的 diff 反猜。
    #   R1-A 要证的是「我明确破坏了 X，判据对 X 敏感」；而 diff 只能看到顶层 `reply` 变了，
    #   `stem/options/answer/explanation` 都在 reply 内部 —— 靠 diff 会让覆盖检查永远对不上。
    mutations = falsify.declared_mutations(p)
    results = [
        falsify.evaluate(
            p,
            base,
            falsify.apply(mutation=mut, record=base),
            mutation_input=mut["input"],
            siblings=siblings,
        )
        for mut in mutations
    ]
    covered = {r.input for r in results}
    check("5a 每个 contract_input 都有声明过的 mutation",
          covered == set(p.contract_inputs), f"缺 {set(p.contract_inputs) - covered}")
    check("5b 基线为 pass 且弄坏后不 pass（★ 基线本身就是红的话，这条必然红）",
          all(r.flipped for r in results), str(results))
    check("5c 其余判据不受牵连", all(not r.collateral for r in results))
    check("5d 弄坏后不得抛异常", not any(r.raised for r in results))
    gaps = falsify.coverage(
        registry.for_task("generate"),
        {p.name: {r.input for r in results} for p in registry.for_task("generate")},
    )
    check("5e generate 判据无未覆盖契约输入", not gaps, str(gaps))
```

`_EXPECTED_ITEMS = 26`（Task 4 结束时为 21，本步 +5）。
Run 预期：`ModuleNotFoundError: evaluation.task_eval.falsify`。

**contract_input 路径语法（Task 5 与 Task 7 共用，一处定义）**：

| 写法 | 含义 | 谁能破坏它 | V0 是否查键存在 |
|---|---|---|---|
| `reply#stem` 等 | `reply` 文本内部的语义片段 | gate 的分段夹具（重组 reply，少掉那一段） | **否** —— 由 R1-A 覆盖检查负责 |
| `gold.gold_answer` 等点分路径 | record 里的真实嵌套键 | `pop` / 置 None | **是**（`has_path()`） |
| `top_items[].knowledge_points` | 列表元素下的键 | 逐元素删 | **是**（任一路径可达即算存在） |

★ 这张表就是「P0-2 的取证模型」与「P1-6 的 schema 检查」之间的胶水：两边都用同一套地址，
V0 才不会对 `reply` 内部的片段报「缺键」，R1-A 才不会去 diff 猜输入。

- [ ] **Step 2: 实现 `falsify.py`**

```python
"""R1-A 机械敏感性取证：在 **record 层**弄坏，看判据是否恰好变红。

★ 只动 record，不动 `src/` 产品代码。本模块证明的是「判据吃到了契约点名的输入」，
  **不是**「产品行为正确」—— 语义那一跳由 R1-B（人工对 §3.1 原文签署）负责。
★ 被破坏的是哪个契约输入，由 **mutation 声明表**给出（`declared_mutations()`），
  不从两条 record 的 diff 反猜。原设计用 diff 猜：`stem/options/answer/explanation` 都在
  `reply` 文本内部，diff 只能看到顶层 `reply` 变了 ⇒ `covered == contract_inputs` 必然失败。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evaluation.task_eval import metrics
from evaluation.task_eval.predicates.common import drop_path
from evaluation.task_eval.predicates.registry import Predicate


@dataclass(frozen=True)
class FalsifyResult:
    predicate: str
    input: str  # ★ 来自 mutation 声明，不是 diff 猜的
    baseline: str  # 基线 verdict —— 「基线本就该 pass」这条前提靠它自检
    flipped: bool  # 基线为 pass 且弄坏后不为 pass
    collateral: bool  # 其余判据的 verdict 被牵连改变
    raised: bool  # 判据抛异常 —— 判据本身不健壮


# 同一个契约输入常常需要**多种**破坏才能真正覆盖它的语义：`reply#answer` 既可能整段缺席，
# 也可能出现「A、B 都算对」。所以每个输入返回 op 列表，而不是「一输入一 mutation」。
_REPLY_OPS: dict[str, tuple[str, ...]] = {
    "stem": ("omit_reply_part",),
    "options_or_task": ("omit_reply_part",),
    "answer": ("omit_reply_part", "dual_answer"),  # ★ 缺 dual_answer 就没证过「唯一性」
    "explanation": ("omit_reply_part", "flip_conclusion"),
}


def declared_mutations(pred: Predicate) -> list[dict[str, str]]:
    """把 `contract_inputs` 展开成声明表（破坏动作与被破坏的输入**同源声明**，不靠 diff 猜）。

    每个契约输入至少一条；缺任一 ⇒ `coverage()` 列成缺口 —— 「形式覆盖但语义没覆盖」的拦网。
    ★ 条数会**多于** `len(contract_inputs)`，而 `coverage()` 比的是输入名集合，不受影响。
    """
    out: list[dict[str, str]] = []
    for name in pred.contract_inputs:
        if name.startswith("reply#"):
            ops = _REPLY_OPS.get(name.split("#", 1)[1], ("omit_reply_part",))
        else:
            ops = ("drop_path",)
        out.extend({"predicate": pred.name, "input": name, "op": op} for op in ops)
    return out


def apply(*, mutation: dict[str, str], record: dict[str, Any]) -> dict[str, Any]:
    """按声明破坏 record。**不遍历、不猜。**分段知识只留在 `metrics`（结构真源），此处只调用。"""
    import copy

    broken = copy.deepcopy(record)
    name, op = mutation["input"], mutation["op"]
    tail = name.split("#", 1)[1] if name.startswith("reply#") else name
    if op == "omit_reply_part":
        broken["reply"] = metrics.strip_reply_part(str(record.get("reply") or ""), tail)
    elif op == "dual_answer":
        broken["reply"] = metrics.rewrite_reply_part(
            str(record.get("reply") or ""), "answer", "标准答案：A、B"
        )
    elif op == "flip_conclusion":
        broken["reply"] = metrics.rewrite_reply_part(
            str(record.get("reply") or ""), "explanation", "解析：8 行分 2 路，故组号需 2 位，因此选 A。"
        )
    elif op == "drop_path":
        drop_path(broken, name)
    else:
        raise ValueError(f"未知 mutation op：{op}")
    return broken


def evaluate(
    pred: Predicate,
    base_rec: dict[str, Any],
    broken_rec: dict[str, Any],
    *,
    mutation_input: str,
    siblings: dict[str, tuple[Predicate, dict[str, Any]]] | None = None,
) -> FalsifyResult:
    base_v = _safe(pred, base_rec)
    broken_v = _safe(pred, broken_rec)
    collateral = False
    for _name, (other, rec) in (siblings or {}).items():
        if other.name == pred.name:
            continue
        if _safe(other, rec) != _safe(other, broken_rec):
            collateral = True
    return FalsifyResult(
        predicate=pred.name,
        input=mutation_input,
        baseline=base_v,
        flipped=(base_v == "pass" and broken_v != "pass"),
        collateral=collateral,
        raised=("raised" in (base_v, broken_v)),
    )


def _safe(pred: Predicate, rec: dict[str, Any]) -> str:
    try:
        return str(pred.fn(rec))
    except Exception:
        return "raised"


def coverage(preds: list[Predicate], covered: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    """返回 {判据名: 未被任何 mutation 覆盖的 contract_input}。非空 ⇒ R1-A 不过。"""
    return {
        p.name: tuple(i for i in p.contract_inputs if i not in covered.get(p.name, set()))
        for p in preds
        if any(i not in covered.get(p.name, set()) for i in p.contract_inputs)
    }
```

`falsify.py` **不需要** `to_record_value`（它比较的是 verdict 字符串）；verdict→落盘三态的映射只在
Task 4 的 `report.py`/`cli.py` 里用 `common.to_record_value`。★ 别在 falsify 里留未使用的导入，
ruff 钩子会在 commit 时直接拦下。

- [ ] **Step 3: gate 里的分段夹具（record 层弄坏的唯一手段）**

`scripts/evidence_chain_gate.py` 内实现夹具（**测试侧**，不进 `src/`）：

```python
def _gen_reply(
    *,
    stem: str = "设 Cache 采用 2-Way 组相联，主存 64 块，Cache 8 行，问组号需要几位。",
    options: str = "A. 2\nB. 3\nC. 4\nD. 6",
    answer: str = "标准答案：B",
    explanation: str = "解析：8 行分 2 路，故 8/2=4 组，组号需 2 位……因此选 B。",
) -> str:
    parts = {"stem": stem, "options_or_task": options, "answer": answer, "explanation": explanation}
    return "\n\n".join(v for v in parts.values() if v)


def _base_record(**overrides) -> dict:
    """falsify 的基线 record：四段齐全、答案键与解析结论**自洽**（都指 B）。"""
    rec = {
        "task": "generate",
        "case_id": "falsify-1",
        "reply": _gen_reply(),
        "top_items": [{"knowledge_points": ["co.overview"]}],
        "gold": {
            "gold_answer": "B",
            "gold_source_ref": {"gold_answer": "knowledge/co/ch3.md#组相联"},
            "expected_kp": ["co.overview"],
        },
        "item_reasons": {},
    }
    rec.update(overrides)
    return rec
```

★ **夹具不变量（计划层面钉死，不留给执行时临场发现）**：每条取证的基线 record 必须让
**目标判据 = `pass`**，且**同级其余判据在基线与弄坏后都不变**。所以基线文案是自洽的
（`标准答案：B` + 解析结论 `B`）；`gen_analysis_agreement` 的红由 mutation 制造
（`falsify.apply` 把 `reply#explanation` 换成结论为 A 的版本），而不是把基线本身写坏。
`FalsifyResult.baseline` 字段就是为了让这条前提可断言 —— 若基线不是 `pass`，`5b` 必然红，
那时**改夹具或改判据**，二者必居其一，不允许放宽 `flipped` 的定义。

`gen_answer_key_validity` 契约第 ② 条（键数恰好为 1）由 `_REPLY_OPS["answer"]` 里的
`dual_answer` 负责证：把答案段改成 `标准答案：A、B` 后判据必须变红。
★ 少了这条 op，「two correct options」在 R1-A 里就是**形式覆盖、语义没覆盖** ——
输入名齐了，语义一条没测。这也是为什么 `declared_mutations()` 按「输入 → op 列表」建模。

- [ ] **Step 4: 把取证结果落盘成 ledger 的输入**

Task 6 的 `derive_status(..., falsify_passed=?)` 需要一份「哪些判据被证过」的机器可读结果，
不能靠人去回忆跑过没有。在本 Step 加一个写盘入口（`scripts/evidence_chain_gate.py` 的 `--emit`）：

```python
def emit_falsify_report(path: str = "evals/claims/falsify_latest.json") -> None:
    import json
    from pathlib import Path

    from evaluation.task_eval import falsify
    from evaluation.task_eval.predicates import registry

    rows = []
    for pred in registry.for_task("generate"):
        base = _base_record()
        siblings = {q.name: (q, base) for q in registry.for_task("generate") if q.name != pred.name}
        results = [
            falsify.evaluate(
                pred,
                base,
                falsify.apply(mutation=mut, record=base),
                mutation_input=mut["input"],
                siblings=siblings,
            )
            for mut in falsify.declared_mutations(pred)
        ]
        rows.append(
            {
                "predicate": pred.name,
                "inputs": [r.input for r in results],
                "all_flipped": all(r.flipped for r in results),
                "no_collateral": all(not r.collateral for r in results),
                "no_raise": all(not r.raised for r in results),
                "baselines_pass": all(r.baseline == "pass" for r in results),
            }
        )
    Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

`_base_record()` 见 Step 3（不分任务，取 generate 的自洽基线）。非 generate 任务的夹具在
Task 8/9 各自补：Memory 的取证走 `read_status` 注入，rerank 的走 `_derive_rerank_status` 直接调用
—— 见那两个 Task。★ `baselines_pass` 这一列是 Step 3 那条夹具不变量的落盘形式，
Task 6 读它来推 `falsify_passed`。

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`
Expected: `全绿`（若 5b 红，说明某判据其实只读了 `reply` 的一个片段 —— **正是 R1-A 要抓的事**，
按判据补实 `contract_inputs` 与 `fn`，**不要**放宽 mutation 让它过）。

- [ ] **Step 5: 提交**

```bash
git add src/evaluation/task_eval/falsify.py evals/datasets/falsify/ scripts/evidence_chain_gate.py
git commit -m "feat(eval): falsify —— mutation 覆盖 contract_inputs（R1-A 取证）"
```

---

## Task 6: 状态三态推导 + ledger 生成 + R3 检查器

**Files:**
- Create: `src/evaluation/task_eval/claims.py`
- Create: `scripts/build_claim_ledger.py`
- Create: `evals/claims/.gitkeep`
- Test: `scripts/evidence_chain_gate.py`（`check_6`）

**Interfaces:**
- Consumes: `falsify.FalsifyResult`、`registry`、`report.build_report`、归档 provenance
- Produces:
  - `CLAIM_PROVEN / CLAIM_MEASURED / CLAIM_UNMEASURED` 三个常量
  - `claims.derive_status(claim: dict, *, falsify_passed: bool, tier_ok: bool, discriminating: bool, provenance_match: bool, signed: bool) -> str`
  - `claims.artifact_status(path: str, *, superseded_by: str = "", reason: str = "") -> dict`
  - `scripts/build_claim_ledger.py --check` → 退出码 0/1（红灯 = 有孤立结论 或 ledger 与重算不一致）

- [ ] **Step 1: 写红的判据（含「已证明」四条件缺一不可）**

```python
def check_6() -> None:
    from evaluation.task_eval import claims as cl

    ok = dict(falsify_passed=True, tier_ok=True, discriminating=True, provenance_match=True, signed=True)
    check("6a 五条件齐 ⇒ proven", cl.derive_status({}, **ok) == cl.CLAIM_PROVEN)
    for key in ok:
        bad = {**ok, key: False}
        check(
            f"6b 缺 {key} ⇒ 不得 proven",
            cl.derive_status({}, **bad) != cl.CLAIM_PROVEN,
        )
    check("6c provenance 不符自动降级（§9 三态推导取证行）",
          cl.derive_status({}, **{**ok, "provenance_match": False}) == cl.CLAIM_MEASURED)
    # tier_ok 的两个前置必须是**算出来的**，不是文档里写「已有抖动数据」
    check("6d 边界档不足 ⇒ boundary_calibrated=False（实测 calibration_30 = {5:28,2:1,0:1}）",
          cl.boundary_calibrated([5.0] * 28 + [2.0, 0.0]) is False)
    check("6e 边界两侧各 ≥3 ⇒ True",
          cl.boundary_calibrated([5.0, 5.0, 5.0, 3.0, 3.0, 3.0]) is True)
```

`_EXPECTED_ITEMS = 35`（Task 5 结束时为 26，本步 +9：6a/6b×5/6c/6d/6e）。

- [ ] **Step 2: `claims.py` 实现**

```python
"""主张状态推导（EVIDENCE_CHAIN.md §1.1）。状态是算出来的，不是写出来的。"""

from __future__ import annotations

CLAIM_PROVEN = "已证明"
CLAIM_MEASURED = "已测量未证明"
CLAIM_UNMEASURED = "未测量"


def derive_status(
    claim: dict,
    *,
    falsify_passed: bool,
    tier_ok: bool,
    discriminating: bool,
    provenance_match: bool,
    signed: bool,
) -> str:
    """★ 参数叫 `falsify_passed` 而不是 `falsified`：`falsified` 字面意思是「主张被证伪」，
    读 `if falsified: return CLAIM_PROVEN` 会把意思整个反过来。这里为真表示
    「mutation 取证成功：判据对它声明的每个契约输入都敏感」。"""
    if not discriminating and not falsify_passed:
        return CLAIM_UNMEASURED
    if not (falsify_passed and tier_ok and discriminating and provenance_match and signed):
        return CLAIM_MEASURED
    return CLAIM_PROVEN


def artifact_status(path: str, *, superseded_by: str = "", reason: str = "") -> dict:
    return {
        "path": path,
        "status": "superseded" if superseded_by else "active",
        "superseded_by": superseded_by,
        "reason": reason,
    }
```

- [ ] **Step 3: `tier_ok` 的两个前置怎么算（§1.3）**

`derive_status(..., tier_ok=?)` 不能靠人写「抖动已量化」。`claims.py` 补两个纯函数：

```python
def boundary_calibrated(
    human: list[float], *, threshold: float = 4.0, min_each: int = 3
) -> bool:
    """judge 在**门槛边界两侧**都见过人工分，才算校准过。

    ★ 门槛一律是 `final_quality ≥ 4`，所以只有 5 分的校准集证明不了「3 分该判不过」。
      实测 `evals/datasets/demo/calibration_30.jsonl` 的 human 分布 = {5×28, 2×1, 0×1}
      ⇒ below=2 < 3 ⇒ False。这不是缺陷，是**尚未做过的事**，必须如实进状态词。
    """
    below = sum(1 for h in human if h < threshold)
    above = sum(1 for h in human if h >= threshold)
    return below >= min_each and above >= min_each


def repeat_jitter(by_run: list[dict[str, float]], *, case_ids: list[str]) -> dict[str, float]:
    """同 case 跨重复运行的 `final_quality` 极差。缺重复运行 ⇒ 返回 {}（= 未量化）。"""
    out: dict[str, float] = {}
    for cid in case_ids:
        vals = [r[cid] for r in by_run if cid in r]
        if len(vals) >= 2:
            out[cid] = max(vals) - min(vals)
    return out
```

`build_claim_ledger` 的 `tier_ok` 取值规则（写进 ledger 的「前置」列，让读者看得见依据）：

| 指标 tier | `tier_ok = True` 的条件 |
|---|---|
| 0 / 1 | 恒 `True`（机械证据不需要校准） |
| 2 | `boundary_calibrated(...) is True` **且** `repeat_jitter(...)` 非空 |

★ 补边界档要**人工标 3/4 档样本**（零 token，另计约 1 人时）；不标的话，QA/Verify/Grade
三个 tier-2 门槛行就停在「已测量未证明」—— 这是**允许的结果**，不是要绕过的失败。
`scripts/evidence_chain_gate.py` 里加一条读真实校准集的判据（不放夹具值，防止以后有人只测夹具）：

```python
    from evaluation.task_eval import claims as cl

    human = [
        float(json.loads(line)["human_score"])
        for line in Path("evals/datasets/demo/calibration_30.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.startswith("#")
    ]
    check("6f 真实校准集的边界覆盖状态被如实记录", cl.boundary_calibrated(human) is False)
```

`_EXPECTED_ITEMS` 从 35 升到 36（本步 +1）。**若**将来补齐了边界标注、此判据变 True，
就把这条判据改成断言 True 并在 commit message 里引用 §7.2 —— 判据跟着事实走，不是跟着愿望走。

- [ ] **Step 4: `build_claim_ledger.py` 生成 `evals/claims/ledger.md`**

必需内容（按 §6 门槛行逐条）：`维度 | 主指标 | 数值或 N/A | 状态词 | 证据锚点 | 复现命令 | R1-B 签署`。
★ 数值一律从归档经 `predicates` 重算，**代码里不允许出现任何手写的百分数字面量**。
命令签名：

```python
    ap.add_argument("--records", required=True, help="效果归档 jsonl（可逗号分隔多份）")
    ap.add_argument("--falsify-report", default="evals/claims/falsify_latest.json")
    ap.add_argument("--out", default="evals/claims/ledger.md")
    ap.add_argument("--check", action="store_true", help="只校验：文档引用与重算是否一致")
```

- [ ] **Step 5: R3「孤立结论」检查器（禁止的是无来源的可验证断言，不是结论句）**

```python
_ORPHAN_RE = re.compile(
    r"(应为空|逐位相同|全绿|一致|通过率|达线|不达线|\d+\.\d{3})"
)
_SOURCED_RE = re.compile(r"(证据：|复现：|`[a-z_]+ [\w\-./]+`|ledger\.md#)")


def orphan_lines(md_path: Path) -> list[int]:
    """含可验证事实但 100 字符内找不到来源锚点的行。"""
    text = md_path.read_text(encoding="utf-8")
    bad = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _ORPHAN_RE.search(line) and not _SOURCED_RE.search(line):
            bad.append(i)
    return bad
```

`--check` 时扫 `docs/EXPERIMENTS.md`、`docs/README.md`、`README.md`、`CLAUDE.md`，
输出行号清单并**返回 1**（本 Task 只报警不阻塞：历史文档大量既有结论句需要逐条补锚点，
那是 Task 10 的收尾工作，不该在此处把 CI 式红灯提前点亮）。

- [ ] **Step 6: 转绿 + 生成一次 ledger 试跑（零 LLM）**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py \
  --records evals/results/task_eval/ec_r1_final_gate.jsonl --out evals/claims/ledger_draft.md
```
Expected: `全绿`；`ledger_draft.md` 里 Generate/Grade 行状态为 **未测量**（gold 未填），
其余行按 §6 逐条有状态词。

- [ ] **Step 7: 提交**

```bash
git add src/evaluation/task_eval/claims.py scripts/build_claim_ledger.py evals/claims/
git commit -m "feat(claims): 三态推导 + tier_ok 两个前置 + ledger 生成 + R3 孤立结论检查器"
```

---

## Task 7: V0 —— schema 完整性与「未测量判据不得进门槛」

**Files:**
- Modify: `src/evaluation/task_eval/gold_sanity.py`（新增 V0 段）或 Create `src/evaluation/task_eval/schema_gate.py`
- Modify: `scripts/build_claim_ledger.py`（`--check` 调 V0）
- Test: `scripts/evidence_chain_gate.py`（`check_7`）

**Interfaces:**
- Consumes: `registry`（判据声明的 tier 与 `contract_inputs`）、归档
- Produces: `schema_gate.check_archive(path: str) -> list[str]`（错误清单，空 = 通过）、
  `schema_gate.assert_no_default_masking(module_pkg: str) -> list[str]`（AST 扫 `.get(k, False)` / `.get(k, 0)`）

- [ ] **Step 1: 写红的判据**

```python
def check_7() -> None:
    from evaluation.task_eval import schema_gate as sg

    bad = {"task": "generate", "case_id": "z", "reply": ""}  # 缺 item_reasons / gold
    errs = sg.check_archive_records([bad])
    check("7a 缺字段 ⇒ 报错，而不是默认 False 通过", bool(errs))
    hits = sg.assert_no_default_masking("evaluation.task_eval.predicates")
    check("7b predicates 包内无 .get(k, False) 掩盖", not hits, "; ".join(hits))
    check("7c 任一 required 判据 missing_premise ⇒ 该 claim 不可进门槛",
          sg.gate_rejects({"gen_correctness": "missing_premise"}) is True)
    check("7d 全 not_applicable 且非 required ⇒ 不阻塞（§8 划清）",
          sg.gate_rejects({"gen_difficulty": "not_applicable"}) is False)
    # ★ 这一条钉住「生产者先于消费者」：registry 查不到判据 ⇒ required 为空 ⇒ gate_rejects 静默 False
    empty_required = [t for t in ("generate", "verify", "memory") if not sg.required_predicates(t)]
    check("7e required_predicates() 对三个任务都非空（防 V0 因空集合静默放行）",
          not empty_required, f"registry 缺：{empty_required}")
```

`_EXPECTED_ITEMS = 41`（Task 6 结束时为 36，本步 +5：7a/7b/7c/7d/7e）。

- [ ] **Step 2: 实现 `schema_gate.py`**

```python
"""V0：正式实验的前置闸（EVIDENCE_CHAIN.md §8）。

★ 阻塞范围刻意划清：只拦「把未证明的东西当成绩」，不拦「披露为 limitation」。
  否则本方案会在答辩日之前把自己锁死。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from evaluation.task_eval.predicates import registry

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


def assert_no_default_masking(pkg: str) -> list[str]:
    """AST 扫 predicates 包：判据里禁止 `.get(k, <非 None 默认>)`。

    判据必须显式区分「没有这个字段」与「有字段且值为假」，否则 V0 就形同虚设。
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
```

本模块不再需要任何「reply 片段名单」——`reply#` 前缀的判定由 Task 3 的 `common.is_reply_part()`
负责，路径解析由 `common.has_path()` 负责，所以 `schema_gate.py` 顶部这样导入：

```python
from evaluation.task_eval.predicates.common import has_path, is_reply_part
```

★ 语法实现只有一份（Task 3 建、Task 5 用、Task 7 用）。如果这里再写一份 `_REPLY_PARTS` 名单，
就是第三套真源 —— 本计划要消灭的正是这种东西。

本 Task 结束时 `_EXPECTED_ITEMS = 41`（Task 6 结束时为 36，`check_7` 贡献 5 项：7a/7b/7c/7d/7e）。

- [ ] **Step 3: `build_claim_ledger --check` 先跑 V0，红灯即退出 1**

```python
    errs = schema_gate.check_archive_records(all_records)
    if errs:
        print("V0 红灯：正式实验禁止依赖未测量 predicate")
        for e in errs:
            print("  -", e)
        return 1
```

- [ ] **Step 4: 转绿并验证「V0 真的拦得住 §4.2 那个事故」**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py \
  --records evals/results/task_eval/phase1_final_gate_20261008.jsonl --check
```
Expected: gate 全绿；ledger `--check` **退出码 1**，且原因包含 `gen_correctness: missing_premise`。
★ 这条退出码非 0 是本计划的**目的**而不是事故。

- [ ] **Step 5: 提交**

```bash
git add src/evaluation/task_eval/schema_gate.py scripts/build_claim_ledger.py scripts/evidence_chain_gate.py
git commit -m "feat(eval): V0 schema 完整性 + 未测量判据禁进门槛（阻塞范围已划清）"
```

---

## Task 8: 归因前置 —— B7 检索失败传播 + judge 的 tier-0 门 + `memory_read_status`（B4）

★ **B7 从 Task 9 挪到这里**，因为 Task 8 的归因门要读 `retrieval_status == "error"`，
而那个值今天**不可达**：`bm25.py:54-59` 把取 collection 失败咽成 `return []`，探针看到的是
「查了、结果为空」⇒ 写成 `empty`。先修生产者，再写消费者，否则归因门在 B7 之前永远看不到 `error`，
「路由坏了」会继续伪装成「没查到」。

**Files:**
- Modify: `src/rag/bm25.py:50-62`、`src/rag/vectorstore.py:142,340`、`src/rag/routes.py:348-350`
  （★ 原 Task 9 Step 1 的 B7 全部搬到这里）
- Modify: `src/evaluation/retrieval_gate.py:1038,1262`（每条 query 前 `reset_query_failures()`）
- Modify: `src/evaluation/task_eval/judge.py:360-400`（`mechanical_reasons_from_record` / `apply_judge_to_dict`）
- Modify: `src/evaluation/task_eval/metrics.py:47-60`（`_PRIMARY_PRIORITY` 不动，写入侧加门）
- Modify: `src/agents/teaching_graph.py:36-56`、`src/memory/safe.py:14-34`
- Modify: `src/evaluation/task_eval/memory_scorer.py:128-195`
- Modify: `src/evaluation/task_eval/predicates/verify.py`、`predicates/memory.py`
  （★ 这两个文件在 **Task 3** 创建（Task 7 的 `required_predicates()` 需要它们已在 registry 里）；
  本 Task 只**扩展 memory.py 读取 `memory_read_status`**，不动 verify.py 的判据定义）
- Test: `scripts/evidence_chain_gate.py`（`check_8`）+ `scripts/memory_step4fix_gate.py` 增项

**Interfaces:**
- Consumes: `Task 1` 的 `memory_read_status`
- Produces:
  - `safe_remember(..., label=...) -> tuple[T | None, str]` —— 新增第二个返回值表状态；
    或（若不改签名更稳）新增 `safe_remember_status()` 并保留原函数供写侧使用 —— **二者择一，
    由本 Step 的实现者按调用点数量决定并在 commit message 里写明**（当前 `safe_remember` 调用点见 Step 4）
  - `memory_scorer.judge_memory_mechanically(..., read_status: str) -> MemoryJudgement`

- [ ] **Step 1: 写红的判据（四种 read_status 的映射表逐条钉）**

```python
def _gold(*, should: bool = True, values: tuple[str, ...] = ("平衡二叉树",)):
    """造一份可机械判定的 gold。

    已核实的真源：`cases.py:85` ⇒ `MEMORY_TYPES = frozenset({"weak_topics"})`（**只有一个合法值**，
    且 frozenset 不能下标取元素 —— 别写 `MEMORY_TYPES[0]`）；
    `cases.py:120` ⇒ 可机械判定要求 `type ∈ MEMORY_TYPES` ∧ `bool(values)` ∧ `should_be_recalled is not None`。
    """
    from evaluation.task_eval.cases import ExpectedAnswerProperty, ExpectedMemory, Gold

    return Gold(
        expected_memory=ExpectedMemory(
            type="weak_topics", values=list(values), should_be_recalled=should
        ),
        # ExpectedAnswerProperty 全默认 ⇒ forbidden_values 为空 ⇒ correct ≡ used（显式退化，契约里已注明）
        expected_answer_property=ExpectedAnswerProperty(),
    )


def check_8() -> None:
    from evaluation.task_eval.memory_scorer import judge_memory_mechanically as J

    def _v(status: str, cards: list[str], hit: bool = True):
        return J(
            memory_cards=cards,
            reply="平衡二叉树" if hit else "",
            gold=_gold(),
            read_status=status,
        )

    check("8a success+命中 ⇒ recalled_actual True", _v("success", ["数据结构 平衡二叉树"]).recalled_actual is True)
    check("8b success+未命中 ⇒ False", _v("success", ["操作系统 页表"]).recalled_actual is False)
    check("8c empty ⇒ False（读到了，确实没卡）", _v("empty", []).recalled_actual is False)
    check("8d failed ⇒ None（★ 绝不记 False）", _v("failed", []).recalled_actual is None)
    check("8e not_attempted ⇒ None", _v("not_attempted", []).recalled_actual is None)
    check("8f failed 时 recalled_pass 为 None 而非 False", _v("failed", []).recalled_pass is None)
    from pathlib import Path

    sites = [
        p
        for p in (
            "src/evaluation/retrieval_gate.py",
            "src/evaluation/task_eval/runner.py",
            "src/rag/routes.py",
        )
        if "reset_query_failures()" in Path(p).read_text(encoding="utf-8")
    ]
    check("8g reset 被三个取证单元各调一次（只加方法不调用 = B7 没闭合）",
          len(sites) == 3, f"只找到 {sites}")
```

`_EXPECTED_ITEMS = 48`（Task 7 结束时为 41，本步 +7：8a/8b/8c/8d/8e/8f/8g）。
Run 预期：`TypeError: judge_memory_mechanically() got an unexpected keyword argument 'read_status'`
（真实签名是 `(*, memory_cards, reply, gold)` —— 本 Task 给它加第四个 keyword-only 参数）。

- [ ] **Step 2: B7 —— 让 `retrieval_status = "error"` 真的可达**

`bm25.py:54-59` 现在是这样，失败即当作「没查到」：

```python
    except Exception:
        return []
```

改成记录失败并让上层能区分「坏了」与「空」：

```python
    except Exception as e:
        # 词法路由整条坏掉时，旧实现返回 [] 且不记失败 ⇒ retrieval_gate 的
        # unexpected_query_failures 看不见它，所有指标照常「健康」；更糟的是探针会把
        # 「坏了」写成 status="empty"，于是归因层永远没有 `error` 这个证据可用。
        from rag.vectorstore import get_vector_store_manager

        get_vector_store_manager().record_query_failure(
            f"{collection_name}: bm25 {e.__class__.__name__}"
        )
        raise  # 交给调用方收敛为 status="error"；不再伪装成空结果
```

★ 这里选 `raise` 而不是 `return []`，是因为 `retrieval_probe.py:111` 的既有契约就是
**「任何异常都收敛为 `ok=False, status="error"`，不抛出」**——收敛点已经存在，只需要让错误真的发生。
`routes.py:348-350` 的向量分支同理：`logger.warning` 之后要把失败计入 `_query_failures`
（向量路径 `vectorstore.py:340` 已经在记，BM25 与这半边补齐）。

`vectorstore.py` 新增两个方法，并**钉死 reset 的调用时机**（只加方法不规定何时调 = 没修：
`_query_failures` 仍是 append-only，case A 的失败会一路跟着 case B/C）：

```python
    def record_query_failure(self, note: str) -> None:
        self._query_failures.append(note)

    def reset_query_failures(self) -> None:
        """★ 每个「独立取证单元」开跑前调一次，三个调用点缺一不可：
        ① `retrieval_gate` 每条 query 之前；
        ② `task_eval.runner.run_case` 每次检索探针之前；
        ③ `routes._amulti_route_search` 每一**轮**之前（一轮内各路由共享，
           这样一条路由坏了能在该轮的 `unexpected_query_failures` 里看到）。
        """
        self._query_failures.clear()
```

自查三处都真被调用（判据 `8g` 靠它）：

```bash
grep -rn "reset_query_failures()" src | tee /tmp/reset_sites.txt
```
Expected: 恰好 3 处，分别在 `evaluation/retrieval_gate.py`、`evaluation/task_eval/runner.py`、
`rag/routes.py`。少于 3 处 ⇒ B7 未闭合，**停在本 Step**，不要继续往下写归因门。

- [ ] **Step 3: `memory_scorer` 加 `read_status` 参数并前置判定**

在 `judge_memory_mechanically`（`:128`）的断言之前插入：

```python
    if read_status in ("failed", "not_attempted"):
        # ★ 测不到记 None（规则①）。旧实现把「读链故障」和「没有卡」压成同一个 `""`
        #   ⇒ 一次 Store 超时会被记成产品召回失败，直接压低论文里的 Memory 数字。
        return MemoryJudgement(
            should_be_recalled=em.should_be_recalled if em else None,
            read_status=read_status,
        )
```

`MemoryJudgement` 加 `read_status: str = ""`；`judgement_to_dict` 一并输出。

- [ ] **Step 4: 生产侧写状态**

```bash
grep -rn "safe_remember" src scripts | tee /tmp/sr_callsites.txt
```
按结果改 `safe.py`：超时与异常分别返回状态字符串，`teaching_graph.py:43-46` 把状态写进
`memory_read_status`（并经现有捕获通道落到 record）。核心形状：

```python
async def abuild_card_with_status(store, uid: str | None) -> tuple[str, str]:
    if uid is None:
        return "", "not_attempted"          # ★ 今天这条路被压成 ""
    card, status = await safe_remember_status(lambda: abuild_memory_card(store, uid), label="memory_card")
    if status != "success":
        return "", status
    return (card or ""), ("success" if card else "empty")
```

`run_case` 把捕获到的状态写进 `record.memory_read_status`。

- [ ] **Step 5: Verify 归因门（judge 的观点不得越过机械证据）**

`judge.py:360-400`：在合并 `failure_reason` 前加机械门。规则用**仓内既有的值名**，不是新发明的：

| 证据 | 允许的归因 | 禁止 |
|---|---|---|
| `retrieval_status == "error"` | `tool_error`（`judge.py:373` 已经这么判） | ★ 禁止 `retrieval_miss` —— 那是把基础设施故障说成产品能力 |
| `retrieval_status == "empty"` ∧ `pack_nonempty is False` | `retrieval_miss` | — |
| `retrieval_status == "ok"` ∨ `pack_nonempty is True` | — | ★ 禁止任何检索层原因 |

实现：`retrieval_miss` / `retrieval_dropped` / `evidence_pollution` 三个**检索层原因**只有满足第二行
才允许进入 `failure_reason`；judge 单独给的一律落 `judge_failure_reasons`（新增字段，`CaseRecord` 与
`apply_judge_to_dict` 同步），不参与 `pick_primary_failure`。这沿用 `judge_memory_*` 已验证过的隔离模式。

**为什么这是真缺陷而不是措辞**（已实测 `phase1_final_gate_20261008.jsonl` 的 15 条 verify）：
`retrieval_status` 全为 `ok`、`pack_nonempty` 全为 **True**、`evidence_count` 1–5、`hard_fails` 全空，
`primary_failure` 却仍是 `retrieval_miss`×15。机械路径（`judge.py:375-376` 要求 `not pack_nonempty`）
在这里**没触发** ⇒ 那 15 条 `retrieval_miss` 只能来自 judge 的意见，再被 `metrics.py:47-50`
的优先级顶成根因。两个 tier-0 见证都反对的归因，不该有资格当「主要失败原因」。

- [ ] **Step 6: 转绿 + 跑现有 Memory gate（零 LLM 部分）**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_step4fix_gate.py
```
Expected: 两者全绿。`memory_step4fix_gate.py` 需新增「故障注入 ⇒ 三维 None 而非 False」判据，
并把它自己的 `_EXPECTED_ITEMS` 从当前值 **+ 新增项数**（#30 的规矩：声明数与实际数必须相等，
少一项就是「更小的绿」）。★ 若 `read_status` 参数让该 gate 里手写的 record 构造失败，
补默认值 `"success"`（保持既有断言语义不变），不要改断言。

- [ ] **Step 7: 提交**

```bash
git add src/rag/bm25.py src/rag/vectorstore.py src/rag/routes.py src/evaluation/retrieval_gate.py \
        src/evaluation/task_eval/judge.py src/evaluation/task_eval/memory_scorer.py \
        src/agents/teaching_graph.py src/memory/safe.py src/evaluation/task_eval/runner.py \
        src/evaluation/task_eval/predicates/ scripts/evidence_chain_gate.py scripts/memory_step4fix_gate.py
git commit -m "fix(eval,rag): B7 让 error 可达 + 检索层归因只由 tier-0 供给 + memory_read_status 四态"
```

---

## Task 9: 业务链 5.A 余下两项 —— B2 `rerank_status` 与 B1 语义统一（含重录）

★ **B7 已挪到 Task 8**（归因门要读它产出的 `retrieval_status == "error"`，生产者必须先于消费者）。
本 Task 因此只剩 5.A 的另外两项 + 重录基线。

**Files:**
- Modify: `src/rag/pipeline.py:564-593`、`src/rag/reranker.py:200-260`
- Modify: `src/rag/embeddings.py`、`src/rag/layer_recall.py:30-131`、`src/rag/evidence_policy.py:130-145`
- Test: `scripts/evidence_chain_gate.py`（`check_9`）+ `evaluation.retrieval_gate` / `probe_gate`

**Interfaces:**
- Consumes: `Task 8` 已落地的 `reset_query_failures()` / `record_query_failure()`（本 Task 不再碰）
- Produces: `embeddings.similarity_from_distance(distance: float, space: str) -> float`、
  `embeddings.SUPPORTED_SPACES`；`pipeline` 的 rerank 阶段返回 `(docs, rerank_status, ms)`；
  `rerank_used` 变为派生 property

- [ ] **Step 1: 写红的取证判据（先红再实现）**

```python
def check_9() -> None:
    from rag.pipeline import _derive_rerank_status as D

    class _D:
        def __init__(self, md):
            self.metadata = md

    check("9a 开关关 ⇒ off", D([_D({})], active=False, raised=False, empty_result=False) == "off")
    check("9b 抛错 ⇒ failed", D([_D({"rerank_score": 0.1})], active=True, raised=True, empty_result=False) == "failed")
    check("9c 无分降级 ⇒ degraded", D([_D({})], active=True, raised=False, empty_result=False) == "degraded")
    check("9d 合法 0.0 分仍是 success（★ on 路由不被误翻）",
          D([_D({"rerank_score": 0.0})], active=True, raised=False, empty_result=False) == "success")
    check("9e 空 docs 不得因 all([]) == True 被判 success",
          D([], active=True, raised=False, empty_result=False) == "degraded")
```

`_EXPECTED_ITEMS = 53`（Task 8 结束时为 48，本步 +5：9a/9b/9c/9d/9e）。
Run 预期先红：`ImportError: cannot import name '_derive_rerank_status'`。
★ 原 `9f`（reset 三处调用）跟着 B7 一起搬进 Task 8，现在是那里的 `8g`。

- [ ] **Step 2: B2 —— `rerank_status` 四值 + 派生 `rerank_used`**

`pipeline.py:593` 的 `return out, True, elapsed_ms` 改为返回真实状态；判定用**键存在**，不用真值：

```python
    def _derive_rerank_status(docs: list, *, active: bool, raised: bool, empty_result: bool) -> str:
        if not active:
            return "off"
        if raised or empty_result:
            return "failed"
        if not docs:
            # ★ Python 的 `all([])` 是 True：不先挡空，`docs=[]` 会被判成 success。
            #   四态判据不能依赖「调用方保证 docs 非空」这种口头前提。
            return "degraded"
        # ★ 判「有没有 rerank_score 这个键」而不是「分数是否 > 0」：reranker.py:246 有合法写 0.0
        #   的路径，用真值会把假重排 on 路由的自报值误翻成 False —— 等于借修诚实度偷偷换基线。
        if all("rerank_score" in (d.metadata or {}) for d in docs):
            return "success"
        return "degraded"
```

`rerank_used` 保留为派生：`status == "success"`。落到 `fused.metadata["rerank_status"]`，
`retrieval_gate.py:873` 同时读新旧两个字段（新字段缺 ⇒ `""`，按「未知」处理，不回填）。

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`
Expected: `全绿（53 项）`

- [ ] **Step 3: B1 —— R4 语义统一（唯一换算点）**

`embeddings.py` 新增：

```python
SUPPORTED_SPACES: frozenset[str] = frozenset({"cosine", "l2", "ip"})


def similarity_from_distance(distance: float, space: str) -> float:
    """Chroma 距离 → 相似度（越高越好）。**全仓只允许这一处做尺度换算**（§1.5 R4）。

    ★ 未列出的 space 直接抛错，不返回原值。旧稿那句 `return float(distance)  # ip 本身即相似度方向`
      本身就违反「先测 space，不猜」：Chroma 对 ip 返回内积还是 1−内积，取决于版本与是否归一化，
      猜错的后果是**数值合法但方向反了**的 `EvidenceDoc.score` —— 正是 B1 要消灭的那类错误。
    """
    import math

    if space not in SUPPORTED_SPACES:
        raise ValueError(f"未支持的 hnsw:space={space}；先核实方向，再显式登记进 SUPPORTED_SPACES")
    d = float(distance)
    if space == "cosine":
        return max(0.0, 1.0 - d)
    if space == "l2":
        return 1.0 / (1.0 + math.sqrt(max(0.0, d)))
    return d  # ip：仅在 Step 3.5 的方向实测通过后才算被验过
```

取 space 时**不给默认值**（`"l2"` 那种默认就是猜）：

```python
    space = (collection.get_metadata() or {}).get("hnsw:space")
    if not space:
        raise ValueError(f"{collection_name}: 集合元数据里没有 hnsw:space，方向无法确定")
```

`layer_recall.py:103` 改为传相似度；`:128-131` 的 `reverse=True` 排序因此自然转正；
`evidence_policy.py:138` 同。RRF 融合分改名写进 `metadata["rrf_score"]`，
`EvidenceDoc.score` 从此只有相似度一种语义。

- [ ] **Step 3.5: 每个 space 用真实 fixture 验方向（把「假设」变成「实测」）**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python - <<'PY'
import sys
sys.path.insert(0, "src")
from rag.embeddings import similarity_from_distance
from rag.vectorstore import get_vector_store_manager

mgr = get_vector_store_manager()
for coll in ["co", "ds", "os", "cn"]:  # 四个学科集合，名字以 SUBJECT_COLLECTIONS 为准
    c = mgr.client.get_collection(coll)
    space = (c.metadata or {}).get("hnsw:space")
    raw = (c.query(query_embeddings=[[0.0] * 1024], n_results=3, include=["distances"])
            ["distances"] or [[]])[0]
    sim = [similarity_from_distance(d, space) for d in raw]
    ok = all(x >= y for x, y in zip(sim, sim[1:]))
    print(f"{coll} space={space} raw={raw} sim={sim} 单调不增={ok}")
    assert ok, f"{coll}: 换算后方向可疑，B1 停在这里"
PY
```
Expected: 四个集合都打印出 space 与换算序列且 `单调不增=True`。
★ 任一集合 False 或 space 不在支持表 ⇒ **停止 B1**，先回 spec §5 把这个 space 登记清楚；
不要带着方向可疑的 `score` 去重录 6 条基线（那会把「语义契约不统一」换成「数值合法的反序」）。

- [ ] **Step 4: 重录 6 条路由（机器时间大头，TEI 需就绪）**

```bash
uv run python scripts/tei_ready.py            # 就绪以它为准，/health 200 不算
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -m evaluation.retrieval_gate
ls evals/baselines/                            # 从文件名读出 6 条路由的 (embedding, rerank) 组合
```
逐条按 `evals/baselines/` 文件名对应的 env 组合跑 `--update-baseline`，**每条的 diff 数字
必须记进 `docs/EXPERIMENTS.md` §20.7**（既有纪律：禁止静默重录）。
`probe_gate` 也跑一次（拦「后退」放行「前进」，权威路由需 `GATE_USE_REAL_EMBEDDING=1` 等三个开关）。

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -m evaluation.retrieval_gate`
Expected: 默认路由**逐位复现**（B2 在 `RERANK_ENABLED=false` 下不改行为）；
B1 相关路由允许小幅变化，但**必须在 §20.7 留下「变化多少、为什么可接受」**。

- [ ] **Step 5: 提交**

```bash
uv run ruff check src/ scripts/ && uv run pyrefly check
git add src/rag/ scripts/evidence_chain_gate.py evals/baselines/ docs/EXPERIMENTS.md
git commit -m "fix(rag): B2 rerank_status 四态 + B1 score 语义统一（重录受影响路由基线）"
```

---

## Task 10: 文档收尾 —— 勘误、superseded 标注、limitation 登记

**Files:**
- Modify: `docs/README.md`（4 处 + 新增本方案与 `evals/claims/ledger.md` 索引行）
- Modify: `CLAUDE.md:47`、`README.md:144`（`--dataset` 路径）
- Modify: `docs/EXPERIMENTS.md` §20.7（已知偏离追加四条）
- Modify: `evals/results/task_eval/HANDOVER.md`（活文档：本轮改造的状态）
- Create: `evals/claims/artifact_status.json`

**Interfaces:**
- Consumes: `claims.artifact_status`、`build_claim_ledger --check`
- Produces: 可被 V0/R3 校验的文档终态

- [ ] **Step 1: 勘误一律改成「可重跑命令」形状**

`docs/README.md:40` 的门禁计数、`:73` 的跟踪状态、`:3` 的「标签待打」——
按 §7 的表逐条替换成命令（例：`` `grep -n "^_EXPECTED_ITEMS" scripts/memory_step4fix_gate.py` 的生成值 ``）。
★ 写「129 → 216」这类新数字同样是 R3 违规；数字会漂，命令不会。
每次 Edit 只替换**整行**，替换后立即 `grep -c ""` 复核行数未减少
（本仓 markdown 有过替换吃掉整条 bullet 的事故）。

- [ ] **Step 2: 旧归档标 superseded（不删、不改数值）**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "src")
from evaluation.task_eval import claims

rows = [
    claims.artifact_status(
        "evals/results/task_eval/phase1_final_gate_20261008.jsonl",
        superseded_by="evals/results/task_eval/ec_r1_final_gate.jsonl",
        reason="composite_na_semantics_changed",
    ),
    claims.artifact_status(
        "evals/results/task_eval/phase0_baseline_final.report.md",
        reason="gold_status_claim_corrected",
    ),
]
Path("evals/claims/artifact_status.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"标了 {len(rows)} 份")
PY
```

- [ ] **Step 3: §20.7 追加四条已知偏离**

照 §7 列的四条写，每条带**命令**而不是数字：① §3.1 五项中三项在 P−1 前 `missing_premise`；
② grade gold 两极 ⇒ `score_tolerance@±10` 判别域受限；③ R5 改复合语义，旧归档读数不可沿用；
④ 5.B 延后项 limitation 清单。

- [ ] **Step 4: 数值工件纳入版本控制**

```bash
git status --short -- evals/results/task_eval | grep '^??' | awk '{print $2}' \
  | grep -E '\.(jsonl|json)$' | xargs git add
git ls-files evals/results/task_eval | wc -l
```
Expected: 计数明显上升且 `.jsonl` 出现在 `git ls-files` 里。
★ 只加 `evals/` 下的证据工件；根目录 `checkpoints.db`（38MB）/`store.db`/`chroma_db/` 一律不加。

- [ ] **Step 5: 全量门禁 + ledger 复核**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_step4fix_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -m evaluation.task_eval sanity
uv run ruff check src/ scripts/ && uv run ruff format --check src/ scripts/ && uv run pyrefly check
```
Expected: 全绿。R3 检查器对刚改过的三个文件**行号清空**（`--check` 仍可对全 docs 报警，
剩余历史行进入 §7.3 Freeze 的收尾清单，不阻塞本计划）。

- [ ] **Step 6: 提交**

```bash
git add docs/ CLAUDE.md README.md evals/claims/ evals/results/task_eval/
git commit -m "docs(evidence-chain): 勘误改命令 + 旧归档标 superseded + 数值工件入版本控制"
```

---

## 取证矩阵的落点对照（spec §6 的 9 行 → 本计划）

| spec §6 那行的主张 | 由哪个 Task 的哪条判据证 |
|---|---|
| `gen_structure` 四件套逐个删 | Task 5 `5a`/`5b`/`5c`（`contract_inputs` 全覆盖 + 恰好变红 + 无牵连） |
| `gen_answer_key_validity` 键 ∉ 选项集 / 两正确项 | Task 3 判据实现 + Task 5 `5e`（registry 里声明 `contract_inputs` 后自动进覆盖检查） |
| `gen_analysis_agreement` 解析结论反改 | Task 5 `_REPLY_OPS["explanation"]` 的 `flip_conclusion`（基线自洽，红由 mutation 制造） |
| `gen_coverage` 抹掉一条 `knowledge_points` | Task 7 `7a`（缺键即报，不默认 False）+ Task 5 覆盖检查 |
| Verify 归因（把 `retrieval_status` 改成 `empty` / `error`） | Task 8 Step 5 的 tier-0 归因门（B7 在同 Task Step 2 先落地）+ Task 7 `required_predicates("verify")` |
| Memory 三种 `read_status` | Task 8 `8d`/`8e`/`8f`（failed/not_attempted ⇒ None，绝不出 False） |
| `rerank_status` 注入降级 | Task 9 `9c`/`9d`（degraded ⇒ 派生 False；合法 0.0 分仍 success） |
| R5 复合遇 `missing_premise` | Task 3 `3c` + Task 4 `4a`（报告层回归）+ Task 7 `7c`（门槛拦截） |
| 三态推导 provenance 不符 | Task 6 `6c` |

★ 两件事**机器证不了**，本计划如实标出而不是假装覆盖：
① R1-B 的语义映射（每个判据对 §3.1 原文人工签署一次，见「完成后」）；
② tier-2 门槛行的边界校准（要人工补 3/4 档样本，零 token、约 1 人时，见 Task 6 Step 3）。

---

## 完成后（不在本计划内）

- **P4 §7.3 Freeze 全量重跑**：V0 通过（含 P−1 已填 gold）才允许开始；届时 ledger 的取证时间整体刷新。
- **R1-B 人工签署**：每个判据对着 `EFFECT_PLAN.md` §3.1 原文签一次「已审@版本」，
  这是机器证不到的最后一跳 —— 不要把它写成「已闭合」。
