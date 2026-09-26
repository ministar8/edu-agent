# RERANK 开关机制梳理：现状、缺陷与设计选项

> 用途：为「rerank 开关该怎么设计」提供完整决策依据。
> 依据：2026-09-24 全量代码核实（所有行号经实际读取确认，非估算）。
> 状态：**仅梳理，未改动任何代码**。

---

## 0. 一句话结论

rerank 是否真正执行，由 **3 个输入**经 **3 道闸**决定。问题有两个：

1. **`.env` 的开关（闸 3）位置过深** —— 关闭时只否决 `rerank()` 自身，否决不到调用者，
   导致下游仍执行重排阈值过滤，把结果**静默截断到 2 条**。
2. **`use_rerank` 被复用了三种语义** —— 所以「把开关前移」会连带改动候选池大小
   （最多 3× 缩水），这正是「一关就变样」的根源。

**两个问题必须一起解决**，只修其中一个都会踩到另一个。

---

## 1. 现状：完整的判定结构

### 1.1 三个输入

| 输入 | 来源 | 语义 | 生产取值 |
|---|---|---|---|
| `use_rerank` | 调用方传参 | 「这条路径声明支持重排」 | `tools.py:152` 硬编码 `True` |
| `depth.skip_rerank` | `query_classifier.py` 各 depth | 「这类查询主动省延迟」 | 仅 `SHALLOW_DEPTH=True`；STANDARD/DEEP/CODE/TEXT_ONLY 均 `False` |
| `settings.RERANK_ENABLED` | **`.env:22`** | 「这个部署是否启用重排」 | `false` |

### 1.2 三道闸

| # | 位置 | 判据 | 否决范围 |
|---|---|---|---|
| 闸 1 | `retriever.py:839`（`_resolve_retrieval_policy`） | `if depth.skip_rerank and use_rerank: use_rerank = False` | 整段（策略层） |
| 闸 2 | `retriever.py:1038`（`_stage_rerank`） | `if not (use_rerank and filtered):` → 早返回 | 整段（阶段层） |
| 闸 3 | `reranker.py:133`（`rerank()`） | `if not settings.RERANK_ENABLED: return documents[:top_k]` | **仅 `rerank()` 自身** |

**关键**：闸 1/闸 2 检查的是同一个变量 `use_rerank`（闸 1 写、闸 2 读）。
闸 3 是**唯一的配置开关**，且位于**被调用者内部**——这是缺陷 1 的结构性原因。

### 1.3 五个「返回原序」的降级出口（非开关）

| # | 位置 | 触发条件 | 日志 |
|---|---|---|---|
| 4 | `reranker.py:130` | 空输入 → `return []` | —（正常） |
| 5 | `reranker.py:180-182` | `HTTPStatusError` | error |
| 6 | `reranker.py:183-185` | 其他异常 | error |
| 7 | `reranker.py:188-189` | rerank 返回空 | warning |
| 8 | `retriever.py:1057` | `_safe_to_thread` 超时（`default=filtered[:top_k]`） | — |

→ **合计 8 个出口**：3 道闸 + 3 个异常/空降级 + 1 个超时兜底 + 1 个正常空输入。
其中 4–8 是**必要的容错**，不应改动。

### 1.4 两处 rerank 调用点

| 位置 | 对象 | 门控 |
|---|---|---|
| `retriever.py:1047` | 主路径候选 | 闸 2 |
| `retriever.py:1175` | HyDE 内对 `hyde_docs` 的二次 rerank | `if use_rerank and hyde_docs:` |

两处都受闸 3 约束，故 `.env` 关闭时**两处一起失效**。

---

## 2. 关键耦合：`use_rerank` 的三种职责

`use_rerank` 这个名字只描述了职责 ①，但它实际控制三件事：

| 职责 | 位置 | 说明 |
|---|---|---|
| ① 是否执行重排 | `retriever.py:1038`、`1175` | 名副其实 |
| ② **候选池开多大** | `retriever.py:370-388`（`coarse_k`）、`421`（路由上限） | **名不副实** |
| ③ 阈值推导的输入 | `retriever.py:370` 分支 | 与 ② 同源 |

### 职责 ② 的量化影响（实测）

| 场景 | `use_rerank=True` | `use_rerank=False` | 倍数 |
|---|---|---|---|
| 短查询（k=3） | `coarse_k=18` | `7` | 2.6× |
| 普通查询（k=5） | `30` | `10` | 3.0× |
| 长查询（k=8） | `48` | `16` | 3.0× |
| 路由上限（`_route_adaptive_k`） | `min(base, 40)` | `min(base, 20)` | 2× （大 base_k 时生效） |

**推论**：任何「把 `RERANK_ENABLED` 折进 `use_rerank`」的改动，都会让关闭开关时
候选池缩到 1/3 —— **一个部署开关静默改变了召回策略**。

---

## 3. 当前缺陷清单

### D1（严重）：`.env` 关闭时结果被截断到 2 条

**触发条件**：`use_rerank=True`（生产恒真）+ `RERANK_ENABLED=false`（`.env` 现值）+ 查询非 SHALLOW。

**链路**：

```
_stage_rerank（retriever.py:1021）
  ├─ 闸2：use_rerank=True → 通过，继续
  ├─ 调 rerank() → 闸3 否决 → 返回原序，**不写 rerank_score**
  ├─ _apply_rerank_threshold(reranked, min_keep=2)（:1063）
  │     top_score=0 → rel_min=0 → final_min=abs_min=0.15
  │     high_confidence = [d for d in reranked if rerank_score >= 0.15] = []
  │     len([]) < 2 → 兜底 return reranked[:2]        ← 伤害
  └─ return out, True, elapsed_ms（:1065）            ← 谎报
```

**实证**（直接调 `_apply_rerank_threshold`）：

```
输入 6 条（无 rerank_score） → 输出 2 条
对照（有 rerank_score）      → 输出 6 条
```

**影响**：知识讲解每问只拿到 2 条证据（`filtered` 非空时输出恒为 2）。

### D2：`rerank_used` 指标失真

`retriever.py:1065` 在进入重排分支后**硬编码返回 `True`**，未反映 `RERANK_ENABLED` 的否决。
`rerank_used` 经 `_stage_hyde`（`:1500`/`:1506`）最终写入阶段指标（`:1377`、`:1571`）。
→ **阶段追踪会把「没重排」记成「重排了」**。

### D3：误导性日志

D1 的兜底分支会打 `logger.info("Rerank threshold fallback: ...")`（`retriever.py:99-107`），
把「rerank 被关闭」误报成「重排后分数不足」。

### D4：门禁覆盖缺口

门禁 off 路由传 `use_rerank=False`（`retrieval_gate.py:488`）→ **在闸 2 就早返回**
（`retriever.py:1041`）→ **根本不会触达 `_apply_rerank_threshold`**。
故门禁 off 路由与生产 off 路径是**两条不同代码路径**。

---

## 4. 门禁覆盖矩阵

> 状态：**B 组已实施**，矩阵随之更新（见 §8）。

| 门禁路由 | embedding | `RERANK_ENABLED` | `use_rerank` | 等于生产？ |
|---|---|---|---|---|
| `off`（默认） | 假 | `False` | `False` | ❌ 池缩到 1/3 + 假 embedding |
| `on` | 假 | `True` + `USE_FAKE_RERANK` | `True` | ❌ 假 embedding + 假 rerank |
| **`disabled`**（新增） | 假 | `False` | `True` | ❌ 仅 embedding 不同 ← 此前构造不出来 |
| `real+off` | 真 | `False` | `False` | ❌ 池缩到 1/3 |
| **`real+disabled`**（新增） | 真 | `False` | `True` | ⭕ **两个维度都对齐生产** |
| **生产（今天）** | 真 | `False` | `True` | — |

**仍有两处缺口**（`configure_for_gate` 强制）：`USE_FAKE_MODEL=True`（假 LLM）
与 `SEMANTIC_CACHE_ENABLED=False`（关缓存）—— 即使 embedding 与 rerank 都对齐，
LLM 驱动的 decompose / HyDE / verify 仍不是生产行为，缓存也关着。

**结论（已更新）**：`real+disabled` 是**口径上最接近生产**的路由，此前在门禁里构造不出来。
它仍不是逐位等价的生产，但差异已收敛到可明确列举的两项：**假 LLM + 关缓存**。

---

## 5. 设计约束（从缺陷反推）

| # | 约束 | 来自 |
|---|---|---|
| C1 | 部署开关必须**窄作用域** —— 只决定「是否执行重排」，不得改动候选池/阈值/k | D1 的教训 + 职责 ② 的量化 |
| C2 | 开关的否决必须落在**能短路整段**的层级，不能在「被调用者内部」 | D1 的结构性原因 |
| C3 | 不得回写 `use_rerank` 这类**被复用的变量** | C1 的实现要求 |
| C4 | 关闭动作必须**可观测**（有日志），不得静默 | D3 |
| C5 | `rerank_used` 必须反映**真实执行情况** | D2 |
| C6 | 门禁需能**复现生产关闭态** | D4 |

---

## 6. 候选方案

### 方案 A：解耦 —— 判定放在闸 2，独立变量（推荐）

```python
# retriever.py:1038 附近
rerank_active = use_rerank and settings.RERANK_ENABLED   # 独立变量，不回写 use_rerank
if not (rerank_active and filtered):
    if not rerank_active:
        return filtered[: k * 2 if decomposed else k], False, 0.0
    return filtered, False, 0.0
```

- ✅ 满足 C1/C2/C3：`.env` 关闭只跳过重排，`coarse_k` 仍为 18/30/48
- ✅ 满足 C5：`rerank_used` 返回 `False`
- ✅ 门禁两条路由不受影响（门禁本就把两者设成同值）
- ⚠️ 代价：关闭时池偏大，多取了些未重排的候选（轻微浪费，非错误）
- ✅ C6 已解决：门禁补了 `GATE_RERANK_MODE=disabled` 路由（见 §8），
  且实测证明「池偏大」不是浪费 —— `disabled` 的指标**优于** `off`

### 方案 B：一致 —— 判定折进闸 1

```python
# retriever.py:839 附近
use_rerank = use_rerank and settings.RERANK_ENABLED
```

- ✅ 关闭动作彻底（池也跟着切到「无重排」配置，与代码里已有的 else 分支一致）
- ❌ **违反 C1**：一个部署开关静默改变 `coarse_k`（3×）、路由上限、阈值推导
- ❌ 与 `extra="ignore"`、静默降级属同一类病

### 方案 C：拆语义 —— 重命名 + 独立判定（最彻底，改动最大）

把职责拆成两个有名字的概念：

| 概念 | 语义 | 影响 |
|---|---|---|
| `rerank_pool`（由 `use_rerank` 更名） | 「候选池按重排口径准备」 | 仅池大小 |
| `rerank_active` | 「是否执行重排」 | `rerank_pool and RERANK_ENABLED and not skip_rerank` |

- ✅ 语义最清晰，C1–C3 全部满足
- ❌ 触碰多处签名与调用点，回归面最大

### 对比

| | A 解耦 | B 一致 | C 拆语义 |
|---|---|---|---|
| 改动面 | 1 处判定 | 1 处赋值 | 多处签名/调用 |
| 关闭时池大小 | 不变 | 缩到 1/3 | 不变 |
| 违反的约束 | 仅 C6 | **C1** | 无 |
| 推荐度 | **首选 —— 已采纳并落地** | 不推荐 | 后续演进（可选，见 §7） |

---

## 7. 决策与实施结果（2026-09-24）

| # | 问题 | 结论 |
|---|---|---|
| Q1 | 选哪个方案 | **A（解耦）** —— 唯一同时满足 C1/C2/C3 |
| Q2 | 关闭时候选池「偏大」可接受吗 | **接受**。实测 `disabled` 的 `category_precision` 0.9874 > `off` 的 0.9561 —— 偏大反而更好 |
| Q3 | `reranker.py:133` 是否保留为防御网 | **保留**，并补 `logger.warning`（触达即异常） |
| Q4 | 是否补门禁 `disabled` 路由 | **已补**（`GATE_RERANK_MODE=disabled`），见 §8 |
| Q5 | 是否一并修 D2 / D3 | **已修**。D2 由「闸 2 短路」+「门禁新增 `rerank_used` 断言」双重守 |
| Q6 | `.env` 的 `RERANK_ENABLED` 是否改为 `true` | **待定**（未动）—— 属产品决策，不在本次范围 |

### 未采纳：方案 C（拆语义）

C 的运行时行为与 A **完全一致**，唯一收益是消除 `use_rerank` 的命名债；
代价是 **80 处 / 9 文件 / 21 个签名** 的机械改名，且其中 **6 处是字典 key**
（`"use_rerank"` 出现在 metadata 与 retry hints 里），改名后**不会报错、只会静默失配**
—— 尤其 `verifier.py:417`（生产端）→ `retriever.py:1787`（消费端）是**跨模块字符串契约**。
若将来要做，必须先给这些 key 加契约测试（人为改错一边能被抓住）。

---

## 8. 实施结果（2026-09-24）

### A 组：核心修复（已完成）

| 位置 | 改动 |
|---|---|
| `retriever.py`（`_stage_rerank` 前） | 新增 `_warn_rerank_disabled_once()` —— **每进程只 warning 一次**（否则 `.env` 关闭时每条 query 刷屏，`warmup_query_cache` 一次连打 N 条） |
| `retriever.py`（闸 2） | `rerank_active = use_rerank and settings.RERANK_ENABLED`，独立变量、**不回写 `use_rerank`** |
| `retriever.py`（HyDE 二次 rerank） | 条件加 `settings.RERANK_ENABLED` —— 堵住 D2 从 HyDE 复发 |
| `reranker.py`（闸 3） | 补 `logger.warning`（防御网被触发 = 异常信号，每次都要打） |

单元验证（6 条输入 / k=5）：`.env` 关闭 + `use_rerank=True` 从「**2 条 + 谎报 `True`**」
变为「**5 条 + `rerank_used=False` + 1 条告警**」。门禁两条路由不退化。

### B 组：门禁扩展（已完成）

- 布尔 `GATE_USE_RERANK` → 三态 `GATE_RERANK_MODE`（`off`/`on`/`disabled`）；
  非法值**不静默回退**；保留 `GATE_USE_RERANK=1` 作 `on` 的兼容别名
- `SUPPORTED_ROUTES`：`(embed, mode)` → 基线路径，**未登记组合直接拒绝**
- `_meta` 升三态 `rerank_mode`；旧基线的布尔 `rerank_enabled` 做兼容映射
- `RerankObservation` 收集 `rerank_used`；`_assert_route_preconditions` 三分支 + 交叉验证
- 新基线：`evals/retrieval_baseline_fake_disabled.json`

### 实测：四条路由全部通过

| 指标 | `off` | **`disabled`** | `on` |
|---|---|---|---|
| `category_hit_at_1` | 0.9500 | **0.9750** | 0.9750 |
| `category_hit_at_k` | 1.0000 | 1.0000 | 1.0000 |
| `category_mrr` | 0.9750 | 0.9875 | 0.9875 |
| `category_precision` | 0.9561 | **0.9874** | 0.9819 |
| `empty_result_rate` | 0 | 0 | 0 |
| `mean_evidence_count` | 5.1250 | **5.9500** | 4.1500 |

★ **`disabled` 显著优于 `off`** —— 它走 `use_rerank=True`，候选池更大
（`coarse_k` 上限 50 vs 20）。这从数据上证实两点：
① 两条路由**确实是不同配置**，分开基线是必要的（原先的布尔 `_meta` 区分不了）；
② **门禁原来的 `off` 路由低估了生产的检索质量** —— 它是个「缩池版」配置，不代表生产。

### C 组：文档同步（已完成）

`README.md`、`docs/ARCHITECTURE.md`（§6.3）、`docs/ENGINEERING_COMPARISON.md`、
`docs/RETRIEVAL_ROADMAP.md`、本文件 —— 路由数、`GATE_USE_RERANK` → `GATE_RERANK_MODE`、
门禁命令补 `PYTHONPATH=src`（原命令裸跑会 `ModuleNotFoundError`）。

### 仍待办

- **Q6**：`.env` 的 `RERANK_ENABLED` 是否改为 `true`
- **方案 C（可选）**：`use_rerank` 改名 + hints/metadata key 的契约测试
- `real+disabled` 路由尚无基线（需 TEI，可用 `--update-baseline` 生成）

---

## 附：相关代码位置速查

| 文件 | 行 | 内容 |
|---|---|---|
| `.env` | 22 | `RERANK_ENABLED=false` |
| `src/core/settings.py` | 116 | `RERANK_ENABLED: bool = True` |
| `src/agents/tools.py` | 152 | `use_rerank=True`（硬编码，路径声明） |
| `src/rag/retriever.py` | 839 | 闸 1（`depth.skip_rerank`） |
| `src/rag/retriever.py` | 1028 | `_warn_rerank_disabled_once()`（C4 一次性告警） |
| `src/rag/retriever.py` | 1063 | 闸 2（`rerank_active = use_rerank and RERANK_ENABLED`） |
| `src/rag/retriever.py` | 1090 | `_apply_rerank_threshold` 调用（原 D1 伤害点，已修） |
| `src/rag/retriever.py` | 1092 | `return out, True, ...`（原 D2 谎报点，已修） |
| `src/rag/retriever.py` | 370-388 / 421 | `use_rerank` 控制候选池（职责 ②） |
| `src/rag/retriever.py` | 1202 | HyDE 内二次 rerank（已加 `RERANK_ENABLED`） |
| `src/rag/reranker.py` | 133 | 闸 3（`.env` 开关，现为防御网 + warning） |
| `src/evaluation/retrieval_gate.py` | 134 / 177 | `_resolve_rerank_mode()` / `SUPPORTED_ROUTES` |
| `src/evaluation/retrieval_gate.py` | 463 / 600 | mode → settings 覆盖 / 传 `use_rerank=rerank_requested()` |

> 行号为 2026-09-24 A/B 组改动**之后**的位置。
