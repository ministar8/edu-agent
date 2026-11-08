# 基础设施抽离迁移计划（文件级 · 2026-11-07）

> **状态：迁移已完成（2026-11）。** 依据 = `docs/RAG_BOUNDARY_MAP.md` §10 实测 import 图
> + 四问取证（llm_calls / embeddings / vectorstore 的依赖与消费方）。
> 本文只回答「文件怎么搬、壳怎么留、按什么顺序搬」，不改变任何运行时行为。
> **行号均为迁移前坐标**（2026-11-07 实测），搬动后会整体前移/替换。

---

## 0. 结论：三件事，不是一个 `rag/infra/`

实测属性判定标准：**消费方 ≥ 2 个包、且语义与检索策略无关 → 全局基建；
只有 RAG 用、且描述检索语义 → 留在 rag。** 按此标准：

| 模块 | 真实依赖 | 真实消费方 | 去向 |
|---|---|---|---|
| `retrieval/llm_calls.py` 通用骨架 | `core.llm` / `core.settings` / `prompts`（仅版本号） | rag×3 + agents/grading | `core/llm_calls.py` |
| 同上，KV 兜底解析（`score/feedback/...`） | 无（纯文本） | 仅批改语义 | `agents/specialists/grading_salvage.py` |
| `common/embeddings.py` | `core.settings` + `rag.common.errors/metrics` | rag + **memory + evaluation×2** | `infra/embeddings.py` |
| `common/vectorstore.py` + `_vectorstore_*.py` | `core.settings` + `rag.common.{errors,metrics,_metadata_spec}` | rag×20 + evaluation×3（service 只能复刻） | `infra/vectorstore.py` + `infra/_vectorstore_*.py` |
| `common/errors.py` | 仅 httpx / chromadb | rag + **agents/runtime/tools** | `infra/errors.py` |
| `common/metrics.py` | 仅标准库（刻意不 import core.settings） | rag×6 + **evaluation/diagnostics** + tests×2 | `infra/metrics.py` |
| `common/_metadata_spec.py` | 无（纯清洗） | 仅 `_vectorstore_ingest` | `infra/_metadata_spec.py` |

**留在 `rag/common/` 的**：`synonyms.py`（检索词表语义）、`rag_utils.py`（检索文本工具）、
`schemas.py`（检索链 LLM 输出 schema）、`parse_utils.py`（LLM JSON 解析，检索专用）。

### 目标目录树

```text
src/
├── core/
│   ├── settings.py  llm.py  cache.py  kp_vocab.py        # 不变
│   └── llm_calls.py            # ★ 新增：通用 LLM 调用骨架（无 prompts 依赖）
├── infra/                      # ★ 新增顶层包（存储/遥测底座）
│   ├── __init__.py
│   ├── errors.py               # ← rag/common/errors.py            (104)
│   ├── metrics.py              # ← rag/common/metrics.py           (260)
│   ├── embeddings.py           # ← rag/common/embeddings.py        (455)
│   ├── _metadata_spec.py       # ← rag/common/_metadata_spec.py    (190)
│   ├── vectorstore.py          # ← rag/common/vectorstore.py       (140)
│   ├── _vectorstore_base.py    # ← rag/common/_vectorstore_base.py (284)
│   ├── _vectorstore_ingest.py  # ← ...                             (175)
│   └── _vectorstore_query.py   # ← ...                             (218)
├── agents/specialists/
│   └── grading_salvage.py      # ★ 新增：批改 KV 兜底解析（从 llm_calls 拆出）
└── rag/                        # 原路径全部保留兼容壳（见 §3）
```

依赖方向（新不变量）：
`infra → core, schema, 第三方`；`core → schema, 第三方`；`rag/agents/memory/evaluation → infra/core`。
**禁止** `infra → rag/agents/memory/evaluation/prompts/service`，**禁止** `core → infra/prompts/rag`。

---

## 1. 分批顺序与依赖图

```text
Batch A  llm_calls → core + 批改解析归位       （独立，可立即开工）
Batch B  errors / metrics / _metadata_spec → infra   （C/D 的前置底座）
Batch C  embeddings → infra                    （依赖 B：errors/metrics）
Batch D  vectorstore* → infra                  （依赖 B+C）
Batch E  护栏测试收紧 + 文档同步 + 壳删除       （每批随行，最终收口）
```

每批独立提交、独立回归；**不跨批混改**。任何一批失败可单独 revert，不影响其他批。

---

## 2. 文件级迁移清单

### Batch A — `llm_calls` 拆成「通用骨架 + 批改解析」

| 动作 | 源 | 目标 |
|---|---|---|
| `git mv` + 改 import | `src/rag/retrieval/llm_calls.py`（404 行） | `src/core/llm_calls.py` |
| 拆出新文件 | 同上 `:238-404`（`_raw_from_validation_error` / `_salvage_from_raw` 的 KV 部分 / `_try_kv_dict` / `_scan_kv_fields` / `_parse_kv_fields` / `_KV_*`） | `src/agents/specialists/grading_salvage.py`（新增） |
| 兼容壳 | — | `src/rag/retrieval/llm_calls.py` → 转发 `core.llm_calls` |

**A1. 解除 `core → prompts` 依赖（必做，否则分层倒置）**

当前 `llm_calls.py:25` `from prompts import PROMPT_SET_VERSION`；而 `prompts/templates/grading.py:16`
又 `from core.kp_vocab import ...`。把文件搬进 `core` 会让底层依赖上层。
改为**显式参数**（5 个调用点各自传，均是已 import prompts 的文件）：

```python
# core/llm_calls.py
def _trace_config(stage: str, prompt_set_version: str) -> dict: ...

async def call_text(prompt, *, temperature, timeout, stage,
                    prompt_set_version: str = "") -> str | None: ...
def call_text_sync(prompt, *, temperature, stage,
                   prompt_set_version: str = "") -> str | None: ...
async def call_structured[T: BaseModel](prompt, schema, *, temperature, timeout, stage,
                                        prompt_set_version: str = "",
                                        salvage: SalvageFn | None = None) -> T | None: ...
```

**A2. salvage 钩子（保留现有兜底语义）**

- 通用部分留在 `core/llm_calls.py`：`strip_tool_markup()`（原 `_strip_tool_markup`）、
  `_raw_from_validation_error()`、`_try_json_dict()`、`_extract_json_object()`。
- 批改专用 KV 解析搬到 `grading_salvage.py`，导出 `salvage_grading(raw, schema)`。
- `call_structured` 失败后：先跑通用 JSON 兜底，再调用传入的 `salvage`（默认 `None`）。
  行为等价：现有 KV 解析对 `QueryClassifyResult/DecomposeResult` 本来就会 validate 失败，
  只有 `GradingResult` 能救回。
- `llm_calls.py:398` 注释声称「gate `⑨g` 断言覆盖 schema 全部字段」——**全仓不存在该 gate**
  （已 grep 确认）。拆文件时补一个真实测试替代：`tests/test_grading_salvage.py`，
  断言 `{score, feedback, is_wrong, error_analysis, knowledge_points}` 全字段可从裸文本救回。

**A3. import 更新（全量 5 处）**

| 文件:行 | 旧 | 新 |
|---|---|---|
| `rag/retrieval/hyde.py:9` | `from rag.retrieval.llm_calls import call_text_sync` | `from core.llm_calls import call_text_sync` |
| `rag/retrieval/query_classifier.py:13` | `... import call_structured` | `from core.llm_calls import call_structured` |
| `rag/retrieval/query_decomposer.py:30` | `... import (call_structured, call_text)` | `from core.llm_calls import ...` |
| `agents/specialists/grading.py:16` | `from rag.retrieval.llm_calls import call_structured` | `from core.llm_calls import call_structured` + `from agents.specialists.grading_salvage import salvage_grading`；调用处加 `salvage=salvage_grading` |
| 5 个调用点 | — | 补 `prompt_set_version=PROMPT_SET_VERSION` |

不需要改：`scripts/ops/verify_agent_chain.py:305`、`verify_memory_loop.py:143`
（它们补丁的是 `grading_mod.call_structured`，grading 模块属性仍在）。

**A. 完成判据**：pytest 全绿（含新增 salvage 测试）+ 9/5 场景 PASS +
`grep -rn "rag.retrieval.llm_calls" src` 只剩壳文件本身。

---

### Batch B — `errors` / `metrics` / `_metadata_spec` → `infra`

| 动作 | 源 | 目标 |
|---|---|---|
| `git mv` | `src/rag/common/errors.py`（104） | `src/infra/errors.py` |
| `git mv` | `src/rag/common/metrics.py`（260） | `src/infra/metrics.py` |
| `git mv` | `src/rag/common/_metadata_spec.py`（190） | `src/infra/_metadata_spec.py` |
| 兼容壳 | 三个旧路径 | 各自 `from infra.X import *`（`infra` 内显式定义 `__all__`） |
| 新增 | `src/infra/__init__.py`（docstring + 语义说明） | — |

**B1. `__all__` 必须显式**（否则壳的 `import *` 会漏名）：
- `infra/errors.py`：`RagError, RetrievalUnavailable, RagInternalError, classify_retrieval_error`（已有 `__all__`，随文件走）。
- `infra/metrics.py`：`MetricsTimer, MetricsWriter, metrics, DEFAULT_METRICS_PATH`。
- `infra/_metadata_spec.py`：`sanitize_for_chroma`。

**B2. import 更新（全量 14 处）**

| 文件:行 | 改为 |
|---|---|
| `agents/runtime/tools.py:19` | `from infra.errors import RetrievalUnavailable, classify_retrieval_error` |
| `scripts/ops/verify_agent_chain.py:225` | `from infra.errors import RetrievalUnavailable` |
| `rag/common/embeddings.py:17-18` | `infra.errors` / `infra.metrics`（C 批会搬文件，先在本批改路径） |
| `rag/common/_vectorstore_ingest.py:10,12` | `infra._metadata_spec` / `infra.metrics` |
| `rag/common/_vectorstore_query.py:13` | `infra.metrics` |
| `rag/ingest.py:21` | `infra.metrics` |
| `rag/retrieval/retriever_io.py:15` | `infra.metrics` |
| `rag/chunking/cleaner/_stages.py:19` | `infra.metrics` |
| `rag/chunking/splitter/_core.py:33` | `infra.metrics` |
| `rag/retrieval/pipeline/_orchestrator.py:13` | `infra.metrics` |
| `evaluation/diagnostics/telemetry_report.py:83` | `from infra.metrics import DEFAULT_METRICS_PATH` |
| `tests/test_metrics_sampling.py:20` | `from infra.metrics import MetricsWriter` |
| `tests/test_telemetry_report_counts.py:16` | `from infra.metrics import MetricsWriter` |
| `rag/common/errors.py` 壳 | 转发 `infra.errors` |

**B3. 保留 `metrics` 的关键性质**：它**刻意不 import `core.settings`**（只读 `os.environ`，
避免 settings 导入期构造顺序问题）。搬进 `infra` 后此性质必须保留——`infra` 比 `rag` 更底层，
更不能反向依赖。`core/settings.py:73,438` 的注释路径需同步改文字（无行为影响）。

**B. 完成判据**：`grep -rn "rag.common.metrics\|rag.common.errors\|rag.common._metadata_spec" src tests`
只剩三个壳文件；pytest 全绿。

---

### Batch C — `embeddings` → `infra`

| 动作 | 源 | 目标 |
|---|---|---|
| `git mv` | `src/rag/common/embeddings.py`（455） | `src/infra/embeddings.py` |
| 兼容壳 | 旧路径 | `from infra.embeddings import *` |

搬迁同时把文件头两个 import 改成 B 批已完成的 `infra.errors` / `infra.metrics`
（若 B 批已在原路径改过一次，这里只改模块前缀）。

**import 更新（全量 8 处）**

| 文件:行 | 改为 | 说明 |
|---|---|---|
| `memory/sqlite.py:27` | `from infra.embeddings import get_embeddings` | 函数内惰性 import，保持惰性 |
| `evaluation/ragas/adapters.py:199` | 同上 | — |
| `evaluation/task_eval/_runner_support.py:148` | 同上 | 起跑预检 |
| `rag/common/_vectorstore_base.py:18` | `infra.embeddings` | D 批会搬该文件，先改前缀 |
| `rag/common/_vectorstore_query.py:76` | `infra.embeddings` | — |
| `rag/retrieval/semantic_cache.py:301` | `infra.embeddings` | 唯一换算点 |
| `tests/test_query_embedding_cache.py:16` | `from infra.embeddings import ...` | 3 个公开名 |
| `schema/evidence.py:37` | 仅注释路径 | 无代码影响 |

**C. 完成判据**：`grep -rn "rag.common.embeddings" src tests` 只剩壳；
`test_query_embedding_cache.py` 通过（monkeypatch 类方法仍作用于同一类对象）。

---

### Batch D — `vectorstore*` → `infra`

| 动作 | 源 | 目标 |
|---|---|---|
| `git mv` | `src/rag/common/vectorstore.py`（140） | `src/infra/vectorstore.py` |
| `git mv` | `src/rag/common/_vectorstore_base.py`（284） | `src/infra/_vectorstore_base.py` |
| `git mv` | `src/rag/common/_vectorstore_ingest.py`（175） | `src/infra/_vectorstore_ingest.py` |
| `git mv` | `src/rag/common/_vectorstore_query.py`（218） | `src/infra/_vectorstore_query.py` |
| 兼容壳 | 四个旧路径 | 各自转发 `infra.*` |

文件内部互相引用同步改前缀（`rag.common._vectorstore_base` → `infra._vectorstore_base`，
`rag.common._vectorstore_ingest/_query` 同理）。

**import 更新（22 处代码 + 1 处注释）**

| 分类 | 文件:行 |
|---|---|
| rag 入库 | `rag/ingest.py:22`；`rag/ingest_layers/{advanced:15, basic:14, code:16, exams:15, exam_practice:14, learning_paths:15}.py` |
| rag 检索 | `rag/retrieval/bm25.py:41,48`；`layer_recall.py:72`；`routes.py:172,295,301,368,389`；`semantic_cache.py:138,214,574`；`postprocess/_window.py:172` |
| evaluation | `evaluation/task_eval/cli.py:279`；`evaluation/task_eval/runner.py:127`；`evaluation/gates/retrieval_gate/_gate.py:155` |
| service | `service/health.py:69` **仅注释**——可选后续：抽出公开 `infra.vectorstore.client_mode()` 让 health 直接复用，消除手工复刻 |

**D. 完成判据**：pytest 全绿；`grep -rn "rag.common.vectorstore\|rag.common._vectorstore_" src tests`
只剩四个壳；Chroma 单例行为不变（壳与实现指向同一模块对象）。

---

### Batch E — 护栏收紧 + 文档同步 + 壳删除

**E1. 扩展 `tests/test_rag_boundaries.py`**（当前 4 条）：

| 新规则 | 说明 |
|---|---|
| `infra` 只能 import `{core, schema}` + 第三方 | 禁止 `infra → rag/agents/service/evaluation/memory/prompts/db/document_processing` |
| `core` 不得 import `{infra, rag, agents, memory, prompts, service, evaluation}` | 保底 `core` 为最底层；`core → schema` 允许 |
| `memory` / `evaluation` 不得 import `rag.common.{embeddings,vectorstore,errors,metrics}` | 必须走 `infra`；旧登记清单删除对应条目 |
| `agents` 的 `AGENTS_RAG_ALLOWED` 删去 `grading.py` | A 批后 grading 不再依赖 rag，只剩 `tools.py` + `teaching_graph.py` |
| `memory` 的 `MEMORY_RAG_ALLOWED` 删去 `sqlite.py` | C 批后只剩 `topics.py`（SYNONYM_MAP） |

**E2. 文档同步**

| 文件:行 | 内容 |
|---|---|
| `docs/RAG_BOUNDARY_MAP.md:151,167,189` | §10 的 G1/G2/路标 1 更新为「已执行/计划见 INFRA_MIGRATION_PLAN」 |
| `docs/RAG_BOUNDARY_MAP.md:58-59` | §2 存储域/Embedding 停靠点改新路径（迁移后） |
| `docs/ARCHITECTURE.md:308` | `rag/common/vectorstore.py` 引用 |
| `docs/DOCKER.md:151,163,168` | `rag/common/embeddings.py` 引用 |
| `src/rag/README.md` | 模块地图加壳说明（迁移期） |

**E3. 壳删除判据**（全部满足才删，放独立提交）：

```powershell
# 每个壳都应满足：除自身外零引用
grep -rn "rag.retrieval.llm_calls" src tests scripts evals
grep -rn "rag.common.embeddings"     src tests scripts evals
grep -rn "rag.common.vectorstore"    src tests scripts evals
grep -rn "rag.common.errors"         src tests scripts evals
grep -rn "rag.common.metrics"        src tests scripts evals
grep -rn "rag.common._metadata_spec" src tests scripts evals
```

建议壳保留到 A-D 全部合入后再过一轮完整评测（`evaluation/gates` + RAGAS），
确认没有按旧路径动态 import 的脚本后再删。

---

## 3. 兼容壳策略

### 模板

```python
"""已迁移至 ``infra.embeddings``（2026-11-xx，见 docs/INFRA_MIGRATION_PLAN.md）。

保留薄转发一层，供尚未更新的调用方过渡；**新代码禁止从这里 import**。
本文件不含任何逻辑，删除判据见迁移计划 §E3。
"""

from infra.embeddings import *  # noqa: F401,F403
from infra.embeddings import __all__  # noqa: F401
```

### 规则

1. **壳内零逻辑**：只做 `import *` + `__all__` 转发；不写兼容分支、不改签名。
2. **实现模块必须显式 `__all__`**：否则 `import *` 只导出非下划线名，私有常量（如
   `_HNSW_COLLECTION_METADATA`）会悄悄消失——向量库门面自己要用，壳则不必导出。
3. **单例语义不变**：`metrics` 单例、`get_vector_store_manager()` 单例、`get_embeddings()`
   都是模块级对象/函数；壳与实现指向**同一个模块对象**，不会二次构造。
4. **monkeypatch 兼容**：`verify_agent_chain.py` 补丁的是 `grading_mod.call_structured`
   （被 import 进 grading 命名空间的符号），与模块路径无关；`test_query_embedding_cache.py`
   补丁类方法，导入的类对象相同——两个现有打桩点都不受影响。
5. **壳也是护栏对象**：E1 的规则用「禁止清单 + 登记清单」表达，壳文件本身不触发违规；
   新代码若从壳 import，行为上仍可用，但代码评审与 E3 的 grep 会暴露。

### 为什么值得留壳

- `evaluation/` 对 rag 有 25 条 import、`tests/` 有 4 处直接 import、`scripts/` 有 1 处；
  没有壳时每一批迁移都要同时改三个包，失败面被放大，且无法按批回滚。
- 有壳后每批的变更收敛为「一个移动 + 一批 import 更新」，pytest/verify 即可独立验收。

---

## 4. 每批的完成判据（统一命令）

```powershell
.venv\Scripts\ruff.exe check src scripts tests evals
.venv\Scripts\python.exe -m pyrefly check
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH="src"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\ops\verify_agent_chain.py
.venv\Scripts\python.exe scripts\ops\verify_memory_loop.py
grep -rn "<旧路径>" src tests scripts evals   # 只允许命中壳文件
```

任一批不绿 → 不进入下一批；回滚 = `git revert` 该批提交（壳策略保证单批可逆）。

---

## 5. 风险登记

| # | 风险 | 触发点 | 缓解 |
|---|---|---|---|
| R1 | `core → prompts` 分层倒置 | A 批按原样移动 | 执行 A1：`prompt_set_version` 改为显式参数；护栏加「core 不 import prompts」 |
| R2 | **pyrefly 严格化** | `core/llm_calls.py` 与 `src/infra/**` 不在 `src/rag/**` 的放宽名单（`pyproject.toml:145-147`） | 迁移后先跑 pyrefly；若报错，二选一：修注解（优先）或加临时 sub-config `matches = "src/infra/**"`（同 rag 放宽集），并在台账标「T8 收紧时一并处理」 |
| R3 | `metrics` 导入期构造 | 壳与实现双路径 import | 只保留实现模块里的单例；壳 `import *` 转发同一对象，不做 `MetricsWriter()` 二次实例化 |
| R4 | 私有名被外部使用 | 壳 `import *` 不带下划线名 | 已 grep：外部只使用 `get_vector_store_manager` / `get_embeddings` / `MetricsWriter` / `DEFAULT_METRICS_PATH` / `similarity_from_distance` / `query_cache_stats` / `clear_query_cache` / `OpenAICompatibleEmbeddings`，全部公开 |
| R5 | 文档/注释陈旧路径 | DOCKER/ARCHITECTURE/BOUNDARY_MAP/schema 注释 | E2 清单逐条改；不改不影响运行，但会误导下一个读者 |
| R6 | Chroma 客户端模式变化 | `_vectorstore_base` 的 http 探活 / PersistentClient 分支 | 纯文件移动，逻辑零改动；D 批后跑一次 `verify_agent_chain`（检索工具真实调用）+ 一次 ingest dry-run |
| R7 | 测试直接 import 私有名 | 无（已核实） | 若新增，按 R4 处理 |
| R8 | 陈旧 gate 声明 | `llm_calls.py:398` 的「gate ⑨g」并不存在 | A 批补 `tests/test_grading_salvage.py` 作为真实覆盖 |

---

## 6. 规模与工作量（实测行数）

| 批次 | 移动/新增文件 | 行数 | import 更新点 | 预估 |
|---|---|---|---|---|
| A | 2 新（core/llm_calls、grading_salvage）+ 1 壳 | 404 → 约 340 + 70 | 5 | 半天，含新测试 |
| B | 3 移动 + 3 壳 + 1 `__init__` | 554 | 14 | 半天，机械 |
| C | 1 移动 + 1 壳 | 455 | 7 代码 + 1 注释 | 2-3 小时 |
| D | 4 移动 + 4 壳 | 817 | 22 代码 + 1 注释 | 半天，机械 |
| E | 护栏 + 文档 + 删壳 | — | — | 半天（可分两次） |

合计约 **2.5-3 人日**，且每批都可独立交付、独立回滚。

---

## 7. 执行后不变量（护栏将锁住）

1. `rag` 不 import `agents/service/evaluation/db`（现状已真，继续锁）。
2. `infra` 不 import 任何业务包（新锁）。
3. `core` 不 import `infra/prompts/rag/agents/memory/service/evaluation`（新锁）。
4. `memory` 对 rag 只剩 `topics.py`（SYNONYM_MAP 兜底）；`agents` 对 rag 只剩
   `tools.py`（检索主通道）+ `teaching_graph.py`（任务分类）。
5. `embeddings/vectorstore/errors/metrics` 的唯一实现位置在 `infra/`，rag 只留兼容壳。
