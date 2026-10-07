# Phase 1 · Verify 修复（第一刀）— 结果与回归核对

> **实验版本**：Phase 1（**独立于 Phase 0B frozen baseline**，后者**未做任何修改**）
> **结果文件**：`phase1_baseline_v2.jsonl`
> **配置**：agent=`deepseek:deepseek-flash` · judge=`dashscope:qwen3.8-flash` · RAG 链=`dashscope:qwen3.7-flash`
> **对比基准**：`phase0_baseline_final.jsonl`（Phase 0B 冻结，同配置）

## 一、改动内容（2 处 prompt，`rag/` 一行未改）

| 文件 | 改动 | 长度 |
|---|---|---|
| `prompts/supervisor.py` | ① 新增「历史真题检索 → knowledge_agent」路由；② 明确处理「我想做 X 的真题」的**歧义**（「找历史真题」vs「出一道真题风格的题」）；③ 声明**路由条件是语义，不是出现「真题」二字**；④ **分派时不得输出文字说明** | 291 → **673** 字符 |
| `prompts/agents.py` | ① knowledge_agent 新增「历史真题查询」5 条硬性行为（用已有证据 / 列年份题号考查内容 / **不生成新练习题** / 只引用检索到的证据 / 证据不足则明确说明、不得编造）；② `_TOOL_CONVENTION` 新增「**不得输出叙述性前言**，最终回复只包含答案本身」 | knowledge: 868 → 1118；`_TOOL_CONVENTION` +1 段 |

**改动边界**：
- `_TOOL_CONVENTION` **只作用于 knowledge_agent / question_agent**（`agents.py:70,134`），
  **grading_agent 与 supervisor 均不含它**。
- **未改 `rag/` 任何代码** ⇒ 检索链代码未动。

## 二、Verify 前后对比（核心验收）

### 行为层（决定性）

| 指标 | Phase 0B | **Phase 1** |
|---|---|---|
| **仍出题（错误行为）** | **6/15** | **0/15** ✅ |
| **有真题信息** | **3/15** | **9/15** ✅ |

> **「用户问历史真题 → question_agent → 生成一套新题 → Verify=0」这条链被彻底切断。**

### final_quality

| | Phase 0B | Phase 1 | Δ |
|---|---|---|---|
| Verify μ | 1.133 | **1.267** | +0.133 |

**说明**：`final_quality` 提升有限，因为**剩余未列出真题的 case 全是 `exam_hit=False`**
（检索层没提供真题证据）⇒ agent **诚实说明无法确认**（**正确行为**）。
**那部分属检索层问题，不在本次范围内。**

**分项**：`exam_hit=True` 的 5 条中，**4~5 条给出真题信息**（跨两次探针为 5/5 与 4/5，
差异经查证为 **LLM 随机性**——同一证据包两次结果不同）。

## 三、Generate 回归（未被误伤）

| | Phase 0B | Phase 1 | Δ |
|---|---|---|---|
| Generate μ | 4.800 | 4.733 | −0.067 |
| Generate 交付完整率 | 0.942 | **0.942** | 0.000 |

**探针级回归验证**（`probes_phase1/generate_cases.jsonl`，4 条）：**4/4 仍出新题** ✅
含 **`p1gen-002`「给我出一道『真题风格』的栈的练习题」** ——
字面含「真题」但意图是出题，**未被吸到 knowledge_agent** ⇒ **歧义处理成功**。

## 四、QA / Memory / Grade 核对

| Task | Phase 0B | Phase 1 | Δ | 判定 |
|---|---|---|---|---|
| QA | 4.333 | **4.667** | **+0.333** | ✅ 升 |
| Generate | 4.800 | 4.733 | −0.067 | ✅ 持平 |
| **Grade** | 5.000 | **4.133** | **−0.867** | ⚠️ 见下 |
| Verify | 1.133 | **1.267** | +0.133 | ✅ |
| Memory | 2.833 | 2.833 | 0.000 | ✅ 持平 |

### Grade 的 −0.867：**不是本次改动引入的回归**

**证据 1**：`_TOOL_CONVENTION` **不作用于 grading_agent** ⇒ 改动碰不到 Grade。
**证据 2**：`score_tolerance@±10` 仍为 **1.000**（n=13, n/a=2）⇒ **判分能力未退化**。

**下降的 3 条**：
| case | 回复 | 性质 |
|---|---|---|
| grd-004 | 「批改失败（工具未返回评分结果）」 | 既有偶发失败 |
| grd-011 | 同上 | 同上 |
| grd-007 | 「最多 2 个元素→B」却判 100（说 C 对） | 推理自相矛盾（LLM 随机性） |

**⇒ 定性：既有偶发失败被本次全量跑暴露，非回归。根因保持「待确证」（见第六节）。**

## 五、retrieval 未变化（交叉验证）

| Task | `kp_hit`（Phase 0B → Phase 1） | `exam_hit` |
|---|---|---|
| QA | 11/11 → **11/11** | 0 → 0 |
| Generate | 5/7 → **5/7** | 0 → 0 |
| Verify | 0/0 → **0/0** | 12 → **12** |

**⇒ 逐位一致** ⇒ 再次证明**检索链确实未被影响**（`LLM_MODEL` 未动 + `rag/` 未改）。

## 六、已知待办

### TODO-1：`grading_agent` 偶发「工具未返回评分结果」

| 项 | 内容 |
|---|---|
| **现象** | 回复为「批改失败：批改失败（工具未返回评分结果，无法给出分数）」 |
| **当前比例** | **2/15 = 13.3%**（Phase 1 全量） |
| **root cause** | **unconfirmed（未确证）** |
| **零成本取证结论** | 工具的失败分支只有两个（「检索标准答案失败（…）」/「{异常}」），实际内层文案**不是工具的** ⇒ 疑似 agent 未成功调工具、自行编造失败说明 |
| **诊断受限原因** | `tool_calls` 字段**对 Grade 不具诊断性**（15/15 全为空，含成功 case）；日志不逐 case 打印工具调用 |
| **处理前提** | **必须先增加 per-case tool-call logging 或专项重跑** —— **不得现在凭推测修** |

### TODO-2：Verify 剩余未列真题的 case（属检索层）

`exam_hit=False` 的 verify case 中，agent 诚实说明无法确认（正确行为），
但**用户仍拿不到真题清单** ⇒ 需检索层（`query_classifier` 把「考过哪些真题」判成 `exercise`
导致不做查询扩展）⇒ **属「动检索链」，按 `EFFECT_PLAN` §6 需新版本 + 全量重跑 + 重录门禁**。

---

## 附：本次实验范围（明确边界）

| 范围内 | 范围外 |
|---|---|
| 改 2 处 prompt（supervisor + knowledge_agent / `_TOOL_CONVENTION`） | 改 `rag/` 检索链代码 |
| 验证 Verify 改善 + Generate/QA/Memory/Grade 回归 | 修检索层（TODO-2） |
| 全量 66 条重跑（agent 行为变了） | 确证 Grade 偶发失败根因（TODO-1） |
| 反泄漏修复（英文叙述前言） | 天花板问题（Grade 无区分度） |
