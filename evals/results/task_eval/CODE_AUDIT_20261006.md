# 代码审查报告 · 死代码 / 死函数 / bug / 检索层一致性

**初审日期**：2026-10-06 · **清理更新**：2026-10-07
**范围**：`src/`（130 个 .py）+ `scripts/`（64 个 .py），重点 `src/rag/`（37 模块 / 12471 行）
**方法**：`ruff --select F`（pyflakes）+ `vulture 2.16`（死代码）+ 逐项人工核实 + 文档↔代码交叉验证

---

## 〇、总体结论

**代码整体质量高**，未发现高危 bug。以下是**初始审查发现**；P1/P2 清理状态见 §六附。

| 维度 | 初始审查结果 | 当前状态 |
|---|---|---|
| 未使用 import | 1 处（测试脚本） | ✅ 已修，`ruff --select F` 通过 |
| 高置信度（≥80%）死函数 | 0 个 | — |
| 死函数（经人工确认） | 15 个候选（其中 4 个在检索层） | ✅ P1/P2 已清理；待用项保留 |
| 死配置项 | 0 个（77 个配置项全部有效） | — |
| 静默吞异常 | 0 处（`except: pass` 均为有意的多级尝试，末尾有 fallback + 日志） | — |
| 检索层「文档 vs 代码」一致性 | 4 项抽验全部一致 | — |
| 坏代码（逻辑自相矛盾） | 1 处（脚本内） | ✅ 已删 `top_tokens` 恒空键 |

> **时间线**：本报告先记录初始静态扫描结果；其后按用户授权陆续删除 P1/P2 死代码。
> 初始候选清单保留作审计轨迹，当前仍保留的项已标注为「待用/需确认」，不得将初始计数读作当前残余数量。

---

## 一、初始死代码候选清单（15 个，经逐项核实）

判定方法：函数名在全项目 `.py` 中出现次数 = 1（仅定义处），且**排除**框架回调
（FastAPI 路由 / Pydantic 钩子 / LangChain 钩子 / `HTMLParser` 回调 —— 这些由装饰器或基类注册，vulture 会误报）。

### 1.1 检索层（`src/rag/`）—— 4 个

| # | 位置 | 函数 | 说明 |
|---|---|---|---|
| 1 | `rag/cleaner.py:108` | `clean_text` | 实际入库链用的是 `clean_documents`（见 `retrieval_gate.build_index` 的 import） |
| 2 | `rag/fusion.py:207` | `fuse_documents` | ★ **与 `afuse_documents`(222) 函数体逐字相同**，仅异步版被 `retriever.py:228` 调用 |
| 3 | `rag/verifier.py:528` | `is_retrieval_sufficient` | 零调用 |
| 4 | `rag/semantic_cache.py:678` | `compact_jsonl` | 零调用 |

> ★ 第 2 项性质是**重复实现**（同步/异步两份完全相同的代码），删同步版即可，无行为影响。

### 1.2 其他模块 —— 11 个

| # | 位置 | 符号 | 说明 |
|---|---|---|---|
| 5 | `agents/factory.py:95` | `get_assembly` | 零调用 |
| 6 | `agents/factory.py:101` | `all_assemblies` | 零调用 |
| 7 | `core/llm.py:75` | `reset_llm_cache` | 零调用（测试用？但测试里也没用） |
| 8 | `schema/schema.py:91` | `pretty_print` | 零调用 |
| 9 | `schema/task_policy.py:142` | `cache_key_parts` | 零调用（**注意**：`TaskPolicy` 有缓存，此方法疑似「本打算用于缓存键」但未接线） |
| 10 | `evaluation/task_eval/metrics.py:143` | `exam_rank` | 零调用 |
| 11 | `evaluation/task_eval/metrics.py:180` | `question_id_recall` | 零调用（docstring 注明「属 Phase 1」⇒ **待用而非死代码**） |
| 12 | `evaluation/task_eval/metrics.py:192` | `question_id_hit` | 同上 |
| 13 | `evaluation/task_eval/cases.py:328` | `is_frozen` | 零调用 |
| 14 | `evaluation/stage_trace.py:501` | `diff_traces` | 零调用（诊断工具函数） |
| 15 | `tools/imputer.py:889` | `_tokenize_text` | 零调用；`imputer.py:863` 的注释说「合并了原先分散在两处的分词」⇒ **合并后遗留** |
| 16 | `tools/imputer.py:89` | `degraded_ops`（property） | 零调用 |

**另有 1 个死方法是我本轮写的**：`scripts/memory_step5_paired.py:62` `ArmSummary._r`（2 行，定义了但未使用）。

### 1.3 待用（**不是**死代码，勿删）

| 位置 | 符号 | 说明 |
|---|---|---|
| `core/kp_vocab.py:108` | `names_by_subject` | **本轮为缺陷 E 方案 A 新增**，待 E-3（`GRADE_PROMPT` 注入词表）使用 |

---

## 二、坏代码（1 处，逻辑自相矛盾）

### `scripts/legacy_coverage_gap.py:186`

```python
"top_tokens": [w for w, _ in Counter().update(all_tokens) or []] if False else [],
```

**问题（三重）**：
1. `if False else []` ⇒ 该表达式**恒返回 `[]`**；
2. 前半段是**永不执行的死代码**；
3. 即便执行也无效 —— `Counter().update(...)` 返回 `None`，`None or []` ⇒ `[]`，`for w, _ in []` 无迭代。

**性质**：疑似「打算实现但未实现」的占位符，用 `if False` 短路掉了。

**影响面**：**无**。该字段名 `top_tokens` 在全项目**零消费方**
（另一处 `legacy_unanchored_top_tokens`(269) 是**不同字段**，实现正常）。

**建议**：直接删除该键。

---

## 三、检索层一致性审查（文档声称 vs 代码实际）

以 `docs/ARCHITECTURE_RETRIEVAL.md`（as-built 总览）为基准，逐条核对代码。

| # | 文档声称 | 代码实际 | 结论 |
|---|---|---|---|
| 1 | §3.2 **「Chroma score 是余弦距离（越小越好），向量路由必须按 score 升序取前 k」** | `routes.py:220`：`sorted(oversampled, key=lambda pair: (pair[1], content_key(pair[0])))[:k]` | ✅ **一致**（升序，且次级键用内容键保证确定性） |
| 2 | §3.2 **「权重表 `_ROUTE_WEIGHTS` 单一真源 `recall.ALL_ROUTES`」** | `recall.py:354`：`ALL_ROUTES = tuple(dict.fromkeys(route for route, _cat in _ROUTE_WEIGHTS))` | ✅ **一致**（派生而非各自维护） |
| 3 | §6.3 **「门禁语料只含 legacy，不含 L1/L2/L3」** | `retrieval_gate.py:730` 的 `build_index` 按 `rag.ingest.DEFAULT_CATEGORIES`（6 目录）遍历，docstring 详载 2505 vs 4085 对照 | ✅ **一致**（且代码注释已固化该边界） |
| 4 | §1 **不变量③「release 只在 `apply_evidence_policy`；BM25/RRF/reranker 内不做权限判断」** | `postprocess.py` / `reranker.py` / `bm25.py` 中 grep `answer_policy\|exam_resources\|eligibility` **零命中** | ✅ **一致** |

**未发现「代码逻辑与实际逻辑不一致」的情况。**

---

## 四、配置层与异常处理

### 4.1 配置项（77 个）—— 零死配置

用脚本提取 `Settings` 类的全部大写字段，逐一统计项目内引用：

- 初筛出 2 个「零引用」：`DASHSCOPE_API_BASE` / `DEEPSEEK_API_BASE`
- 人工复核 ⇒ **误判**：二者在 `settings.py:386/390` 的 `BASE_URL` property 内部被使用
- ⇒ **77 个配置项全部有效** ✅

### 4.2 异常处理 —— 无静默吞错

检索层 `except: pass` 共 4 处，全部为**有意的多级尝试**：

| 位置 | 性质 |
|---|---|
| `evidence.py:56` | JSON 解析失败 → 下一行有 `return` 兜底 |
| `loader.py:42/66` | 编码候选链（utf-8 → GB 系列 → Big5 → replace），末尾有最终兜底 |
| `parse_utils.py:56/64/72` | 多级 JSON 提取（直接 → 方括号 → 花括号），末尾 `logger.warning` + `fallback_default` |

⇒ 均**有兜底且可观测**，非静默吞错 ✅

---

## 五、vulture 误报说明（供后续复查参考）

vulture 报出大量 `unused attribute`（60%），**绝大多数是误报**：

| 误报类型 | 例子 | 为何误报 |
|---|---|---|
| dataclass 字段 | `task_eval/runner.py` 的 `CaseRecord.*`、`report.py` 的统计字段 | 经 `to_dict()` / `asdict()` 序列化，静态分析看不到 |
| 框架回调 | `service/auth.py` `login`/`register`、`service/service.py` `health_check` | FastAPI 装饰器注册 |
| Pydantic 钩子 | `settings.py:305` `model_post_init`、`schema/task_policy.py` `_reject_*`、`schema/grading.py:47` `_truncate_long_text` | `@field_validator` / `@model_validator` 注册 |
| LangChain 钩子 | `agents/runtime_model.py` `wrap_model_call` / `awrap_model_call` | 基类回调 |
| `HTMLParser` 回调 | `scripts/fetch_408_web.py` `handle_starttag` 等 | 基类回调 |
| 签名兼容参数 | `rag/knowledge_tagger.py:117` `fallback_category` | docstring 明确「未使用（保留签名以兼容调用方）」 |

⇒ **后续复查时应先用 `--min-confidence 80` 过滤**（本次该档位结果为空）。

---

## 六、建议处理清单（按优先级）

### P1 · ✅ **已删除**（2026-10-06，零风险，纯冗余）

| # | 位置 | 符号 | 删除依据 |
|---|---|---|---|
| 1 | `rag/fusion.py:207` | `fuse_documents` | 与 `afuse_documents` 函数体**逐字相同**，仅后者被调用 |
| 2 | `rag/cleaner.py:108` | `clean_text` | 实际入库链用 `clean_documents`；其正则仍被同文件其他函数使用（已核实） |
| 3 | `rag/verifier.py:528` | `is_retrieval_sufficient` | 零调用；`Verdict` 被 `retriever.py` 使用（不受影响） |
| 4 | `rag/semantic_cache.py:678` | `SemanticCache.compact_jsonl` | 零调用；`time`/`json` 仍被其他方法使用 |
| 5 | `scripts/legacy_coverage_gap.py:186` | `top_tokens` 键（**坏代码**） | `if False else []` 恒空 + 零消费方 |
| 6 | `scripts/memory_step5_paired.py:62` | `ArmSummary._r` | 本轮我引入的死方法 |

**删除后验证**：

- `ruff check src/ scripts/` → **All checks passed**
- **模块导入测试**：4 个模块导入 OK；4 个符号确认已移除；`afuse_documents` 仍在
- **vulture 复扫**：5 项**已全部消失**
- **删除当时的回归验证**：`memory_step4fix_gate.py` 的 ❌ 项与删除前完全一致（当时 ⑩d'/⑩d'' 因 embedding 502 失败）；⑪ 组 8 项全绿。
- **后续环境恢复验证（2026-10-07）**：重跑 Gate **全部通过**；⑩d' 写入 2 条，⑩d'' 派生 `['平衡二叉树']`。
- 顺带修正 `scripts/memory_step4fix_gate.py` 的 2 处 `I001`（import 排序，该未跟踪脚本原有）


### 6.1 专项核查：`schema/task_policy.py:142` `cache_key_parts`（P2 第 10 项详述）

**结论**：**是死代码，但非缺陷** —— 它声称的安全不变量**在实现层面以另一种方式满足**。
**这是一处「设计意图 vs 实现路径」的表述不一致**，值得记录。

#### 6.1.1 该方法声称什么

```python
def cache_key_parts(self) -> tuple[str, ...]:
    """语义缓存 key 必含片段（安全隔离）。"""
    return (self.task_mode, self.depth, self.layer_policy_id,
            self.policy_version, self.cache_scope)
```

docstring 断言：**语义缓存的 key 必须包含这 5 个片段**（否则跨策略串味）。

#### 6.1.2 实际缓存 key 是什么

`semantic_cache.py:41` `_cache_key`：
```python
raw = f"{normalized_query}|{collection_name}|{filter_sig}|{params_sig}"
```

| `cache_key_parts` 声称的片段 | 是否进 key |
|---|---|
| `task_mode` | ⚠️ **仅间接**（经 `filter_sig`） |
| `depth` | ✅ 在 `params_sig` 里 |
| `layer_policy_id` | ❌ **不在** |
| `policy_version` | ❌ **不在** |
| `cache_scope` | ❌ **不在** |

#### 6.1.3 逐项追查：为什么「不进 key」也不出事

**① `task_mode` 的间接覆盖**：`retriever.py:144` 的 `_filter_sig` 来自
`agents/tools.py:243` 的 `policy.eligibility_where()`。

各 mode 的 `eligibility_where()`（`task_policy.py:190`）：

| mode | exam_resources (q/a/p) | `ne` 条数 | 返回值 |
|---|---|---|---|
| practice | forbidden/forbidden/forbidden | 4 | 非 None |
| verify | allowed/forbidden/forbidden | 2 | 非 None |
| **explain** | **allowed/allowed/allowed** | **0** | **`None`** ⚠️ |
| grade | allowed/allowed/forbidden | 1 | 非 None |
| learn/method | forbidden/forbidden/forbidden | 4 | 非 None |

⇒ 只有 `explain` 的 filter 为空。**不存在两个 mode 同时为空** ⇒ **无串味**。

**② `layer_policy_id` / `policy_version` / `cache_scope` 为何可以不进 key**：

关键在于**缓存只存「纯检索结果」**，所有 policy 相关处理都在**缓存之外**执行：

| 处理 | 位置 | 相对缓存 |
|---|---|---|
| `aretrieve_evidence_with_retry(...)` | `tools.py:247-258` | **缓存发生处** |
| `_with_topup(...)`（用 `preferred_layers`/`eligible_layers`） | `retriever.py:360` | **缓存之后** |
| `finalize_with_layer_ranking(...)` | `tools.py:262` | **缓存之后** |
| `apply_evidence_policy(...)`（release 裁剪） | `tools.py:263` | **缓存之后** |

且 `aretrieve_evidence` 内部**不 import** `apply_evidence_policy`
（`retriever.py:140-142` 只 import `afuse_documents` / `averify_evidence`）。

⇒ **缓存命中也无法绕过 release 裁剪**（每次都按当前 policy 重做）⇒ **无泄露风险** ✅

#### 6.1.4 判定与建议

| 项 | 结论 |
|---|---|
| 是否死代码 | **是**（零调用） |
| 是否是 bug | **否** —— 安全不变量以「policy 处理置于缓存外」这一更简洁的路径满足 |
| 性质 | **「设计意图 vs 实现路径」的表述不一致**（docstring 按最坏情况列举，实现走了另一条路） |
| 处理 | ✅ **已执行（2026-10-07）**：删除方法 + 把不变量以注释转移到 `_cache_key` 处 |

**★ 必须留注释的理由**：该不变量是**隐式的** —— 它依赖「policy 处理全在缓存外」这一事实。
若将来有人把 `finalize`/`apply_evidence_policy`/`topup` **移进** `aretrieve_evidence`
（看起来是合理的重构），缓存就会**同时缓存掉 policy 裁剪的结果** ⇒ 策略变更后旧缓存继续命中
⇒ **真泄露**。届时必须先让 `cache_key_parts` 进 key。

> 这正是「死代码也可能承载不变量」的典型例子 —— 删除时须把不变量转移到**活代码**处。

#### 6.1.5 执行结果（2026-10-07）

| 动作 | 结果 |
|---|---|
| 删除 `TaskPolicy.cache_key_parts()`（`task_policy.py:142-150`） | ✅ |
| 在 `semantic_cache.py:_cache_key` 补**安全不变量注释**（含「改动须知」警告） | ✅ |
| **保留** `cache_scope` / `policy_version` **字段** | ✅ 二者是 `TaskPolicy` 的策略元数据，删字段会改 schema 且有追溯价值 ⇒ 不删 |

**验证**：`ruff check src/ scripts/` → All checks passed；
`cache_key_parts` 已移除、`_cache_key` 仍在、两字段保留；
删除当时 gate 的 ❌ 项与删除前**完全一致**（当时 ⑩d'/⑩d'' 因 embedding 502 失败）⇒ **无代码回归**；2026-10-07 embedding 恢复后重跑 Gate **全部通过**，⑩d' 写入 2 条、⑩d'' 派生 `['平衡二叉树']`。



### P2 · ✅ **已清理**（2026-10-07，用户确认「一起清掉」）

| 初始候选 | 处理结果 |
|---|---|
| `agents/factory.py` `get_assembly` / `all_assemblies` | ✅ 删除两个访问器，连带移除仅供它们使用的 `AgentAssembly` dataclass、`_ASSEMBLIES` 注册表及写入逻辑；`build_agent()` 仍正常返回 `create_agent()` 图 |
| `core/llm.py` `reset_llm_cache` | ✅ 删除（零调用；测试里也无使用） |
| `schema/schema.py` `pretty_print` | ✅ 删除；其仅调用的 `pretty_repr` 同属零调用，**一并删除** |
| `schema/task_policy.py` `cache_key_parts` | ✅ 删除；安全不变量已转移到 `semantic_cache._cache_key` 注释（详见 §6.1） |
| `evaluation/stage_trace.py` `diff_traces` | ✅ 删除；保留并继续使用更灵活的 `compare_traces` |
| `evaluation/task_eval/cases.py` `is_frozen` | ✅ 删除（零调用） |
| `tools/imputer.py` `_tokenize_text` / `degraded_ops` | ✅ 删除两个零调用包装；保留 `_tokenize_with_positions` 和内部 `_degraded` 状态逻辑 |

**验证**：`ruff check src/ scripts/` → All checks passed；`compileall` OK；vulture 复扫目标 P2 符号全消失；相关 7 模块导入 OK；`ResourceGuard` 的 quota/degrade/reset 行为 smoke-test 通过。

### P3 · 保留（待用 / 计划用途）

| 位置 | 符号 | 原因 |
|---|---|---|
| `core/kp_vocab.py:108` | `names_by_subject` | **缺陷 E 方案 A 的 E-3 会用** |
| `evaluation/task_eval/metrics.py` | `question_id_recall` / `question_id_hit` / `exam_rank` | docstring 标注属 **Phase 1**；Phase 0 用 `exam_hit@5` 代理，暂时未接线但有计划用途 |

### P4 · ✅ 已修

- `scripts/memory_step4fix_gate.py` 的 `_resolve_config` 未使用 import 已移除；`ruff` 全量通过。


---

## 七、未覆盖范围（如实声明）

1. **未做全量人工逐行审查** —— `src/` 约 2 万行，本次以「工具筛查 + 关键链路人工核实」为主；
   死代码判定依赖**静态分析**，**动态调用**（`getattr` / 字符串引用 / 插件注册）可能漏判。
2. **检索层的「数值正确性」未验证** —— 本次验证的是**结构与一致性**（排序方向、单一真源、
   门禁边界、不变量），未重跑检索指标（需 embedding 服务，当前 502 不可用）。
3. **`docs/` 下其他文档与代码的一致性未逐条核对** —— 仅以 `ARCHITECTURE_RETRIEVAL.md` 为基准。
4. `scripts/` 下的**一次性脚本**（`fetch_408_web.py` 等）未做深度审查。
