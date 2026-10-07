# evals/results/task_eval/ — 目录约定

## 🔒 冻结基线（**只读**）

| 文件 | 说明 |
|---|---|
| `phase0_baseline_final.jsonl` | **Phase 0B 冻结基线**（66 条，`gold_status=reviewed`） |
| `phase0_baseline_final.report.{json,md}` | 基线报告 |
| `PHASE0_FREEZE.md` | **冻结快照**（配置 / 数字 / calibration / 代码版本 / 已知局限） |
| `PHASE0_STATUS.md` | 进度与换模型影响审理 |
| `phase0_findings.md` | 归因发现（哪些结论成立 / 哪些随模型失效） |
| `probe_verify_phrasing.jsonl` | Verify 问法探针（Phase 0B 阶段） |

**规则**：上述文件**不得原地修改**。
- Phase 1 及以后的所有实验 → **新建文件**，命名带 `phase1_` 前缀。
- 需重算派生指标（如检索侧口径变了）→ 用 `reprobe` / `backfill` **输出到新文件**，不覆盖基线。

## 🧪 Phase 1 实验版本（**独立于 Phase 0B，不改写它**）

| 文件 | 说明 |
|---|---|
| `phase1_baseline_v2.jsonl` | **Phase 1 结果**（Verify 修复后全量 66 条） |
| `PHASE1_VERIFY.md` | **Phase 1 报告**：改动 / Verify 前后对比 / Generate 回归 / QA·Memory·Grade 核对 / retrieval 未变 / 待办 |
| `phase1_verify_probe.jsonl` | 探针 v1（修复前，含英文泄漏 4/14） |
| `phase1_verify_probe_v2.jsonl` | 探针 v2（反泄漏修复后，泄漏 **0/14**） |
| `../datasets/probes_phase1/` | Phase 1 探针集（10 verify + 4 generate 回归） |

**配置**：与 Phase 0B **相同**（agent=`deepseek:deepseek-flash` · judge=`qwen3.8-flash` · RAG=`qwen3.7-flash`）
**差异**：仅 agent 的 **prompt**（supervisor 路由 + knowledge_agent 行为 + `_TOOL_CONVENTION`）

### 验收结论

| 项 | 结论 |
|---|---|
| **Verify 修复** | ✅ **成功**：仍出题 **6/15 → 0/15**；有真题信息 **3/15 → 9/15** |
| **Generate 未误伤** | ✅ 4/4 回归探针仍出新题（含「真题风格」歧义条） |
| **QA / Memory** | ✅ 持平或升 |
| **检索链** | ✅ **逐位一致**（`kp_hit` / `exam_hit` 全同）⇒ 未动 |
| **Grade −0.867** | ✅ **非回归**（既有偶发失败；`score_tolerance` 仍 1.000） |

### 实验范围（明确边界）

| 范围内 | 范围外 |
|---|---|
| 改 2 处 prompt | 改 `rag/` 检索链代码 |
| 验证 Verify + 回归核对 | 修检索层（TODO-2） |
| 全量 66 条重跑 | 确证 Grade 偶发失败根因（TODO-1） |

## 🧠 Phase 1.5 · Memory（**进行中**）

| 文件 | 说明 |
|---|---|
| ~~过程文档（诊断 / 设计 v3 / Step2 设计 / case 重写 / Step4 审阅·修复）~~ | **已整理删除**（移入回收站）—— 属「已落地方案 + 中间产物」，结论已全部提炼进 `HANDOVER.md` §五 |
| **`PHASE1_MEMORY_STEP5_FINDINGS.md`** | **★ 主文档（保留）**：4 缺陷 A–D + 3 缺陷 D2-1/2/3 + **缺陷 E** + 重跑结果 |
| `PHASE1_MEMORY_STEP5_20261006_2144.md` | Step 5 配对对照报告（脚本自动生成，**保留**） |
| `phase1_memory_step5_store_{on,off}.jsonl` | Step 5 原始 record（ON / OFF 两组，**保留**） |
| `phase1_memory_step5_store_{on,off}_pre_fix_20261006_2023.jsonl` | **旧产物数据**（缺陷 A/C 修复前，**不可作基线**） |
| `../datasets/demo/memory_cases.jsonl` | **6 条 Memory case**（`values` 均为已核验 canonical name） |

**核心结论**：跨会话召回**已成立** —— `mem-001` 记忆卡 `【学生记忆】\n薄弱：平衡二叉树`，
ON 组 1 卡 1 召回 / OFF 组 0 卡 0 召回（机械对照，无旁路）。

**未修完**：**缺陷 E** —— 批改产出的 `knowledge_points` 是 LLM 自造自由文本
（`图的基本性质`/`堆的定义`），非 `kp_index` canonical ⇒ 聚合桶互不相同
⇒ `MIN_HITS` 永不满足 ⇒ **正样本召回率被压到 1/3**。修复走**方案 A**（prompt 注入词表）。

**★ 环境依赖**：Memory 写入路径（`aappend_episode`）依赖 embedding 服务（`http://localhost:11435`）。
服务不可用时 `record_grade` 会因超时被 `safe_remember` 静默丢弃，导致「写入/派生」断言变红。
**当前状态（2026-10-07）**：服务已恢复（health/embeddings 均 HTTP 200）；`memory_step4fix_gate.py` 全绿，
含 `⑩d'` 写入 2 条 episode、`⑩d''` 派生 `['平衡二叉树']`。环境故障的历史判别详见 `HANDOVER.md`。

## 📌 TODO（已知问题，**未处理**）

### ~~TODO-1~~ → **已定位并修复（= 缺陷 A）**，2026-10-06 Step 5

| 项 | 内容 |
|---|---|
| 现象 | 回复为「批改失败：批改失败（工具未返回评分结果，无法给出分数）」 |
| 比例 | Phase 0B 实测 **2/15 = 13.3%**；Step 5 专项实测 **62.5%**（8 次批改失败 5 次） |
| **root cause（已确证）** | `feedback` 超长 ⇒ Pydantic `ValidationError` ⇒ `call_structured` 返回 `None` ⇒ 工具回「批改失败」 |
| 诊断方式 | **专项重跑 + 逐条读批改工具的原始异常**（原 TODO 要求的 per-case logging 已落实） |
| **修复** | 三处收口：① `schema/grading.py` 改**截断**（软上限 800/500）；② `GRADE_PROMPT` 加长度约束（≤200/150 字）；③ `rag/llm_calls.py` 加**同 prompt 重试** + 工具标记清洗 + 裸 KV 兜底 |
| **效果** | 修复后 Step 5 ON 组 **6/6 valid**（修复前 1/6） |
| 详见 | `PHASE1_MEMORY_STEP5_FINDINGS.md` §三·缺陷 A |

> 原记录的「`tool_calls` 字段对 Grade 不具诊断性（15/15 全空，含成功 case）」**仍然成立** ——
> 批改工具返回的是**对话体文本**而非 JSON，故 `_parse_tool_payload` 提不出结构。
> 判分只能靠 `grade_scores`（由 `ToolMessage.name` + 正则提分）。

### TODO-2：Verify 剩余 case 属**检索层**

`exam_hit=False` 的 verify case 拿不到真题证据 ⇒ 根因是 `query_classifier` 把
「考过哪些真题」判成 `exercise`（不做查询扩展）⇒ **属「动检索链」**，
按 `EFFECT_PLAN` §6 需新版本 + 全量重跑 + 重录门禁。

## 代码版本对应

```
code_version  = 648d819-dirty
golden_sha256 = be98912a4c91fb88151640c82515127465031c1e79382b99c40e32311d6d1a66
```

⚠️ 该值系**事后补录**（原实现有 bug：`code_version` 从未写入），
66 条记录标有 `provenance_reconstructed: true`。

## 工具命令（零 LLM 成本）

```bash
# 只重跑检索探针，更新检索侧指标
python -m evaluation.task_eval reprobe  --records <in.jsonl> --out <out.jsonl>
# 回填机械可算字段（Generate 交付五项等）
python -m evaluation.task_eval backfill --records <in.jsonl> --out <out.jsonl>
# 只重判不重跑（换 judge 时省 ~85% 调用）
python -m evaluation.task_eval rejudge  --records <in.jsonl> --out <out.jsonl>
# gold 合法性检查（进 0B 前必跑）
python -m evaluation.task_eval sanity
```

## ~~`_archive/`~~ —— **已整理删除**（2026-10-06）

原存放 Phase 0B 的 **45 个中间版本**（baseline v1–v6、grade v3–v5、ds 中间版、各次 `.log`）。
**已移入系统回收站** —— 属「方案期间的中间产物」，最终版已在上一级
（`phase0_baseline_final.jsonl`）。如需追溯，可在回收站按原名恢复。

## ⚠️ 消耗 token 的纪律

`run` / `rejudge`（会调 LLM）**必须先获用户明确授权**才执行。
`reprobe` / `backfill` / `sanity` / `calibrate` 是零 LLM 成本，可直接跑。
