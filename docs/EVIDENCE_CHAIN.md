# EVIDENCE_CHAIN — 证据链重建方案（主张 ↔ 证据对齐）

> 一句话：**把「声称」从人写的措辞，变成机器算出来的状态。**
> **基准代码态**：`3e77e01`（2026-10-08 15:54）。本文引用的所有跟踪状态/归档读数都写成**命令**，
> 不写死数字 —— 本方案自己先遵守 R3。
> v1.2（2026-10-08）：v1.1 并入第一轮 review 的 12 条 + R5；**v1.2 并入第二轮 7 条**
> —— gold 补齐从「可选路线」升级为 **P0 前置**、R5 补**分母语义与 `required_when`**、
> 业务链二分（阻塞正式实验 / 登记 limitation）、新增 **B7 检索失败传播**、V0 加硬、**盲标规程**。
> v1.6（2026-10-09，P−1 裁定三批）：§4.4 冻结「答案形态 / 答案状态 / 四态映射留位 / 父题-part 汇总禁令 /
> 错键扩查五步 / R 行启用与红线」。统计口径改为**三分法**（设计目标 / 实际审计结果 / 可支持结论），
> 并明确强制分层配额下**不得**把简单随机抽样的发现概率当作分层后的总体置信结论。
> v1.5（2026-10-09，P−1 普查后的裁定）：**Generate 的 P−1 目标改了**。普查（`scripts/p1_corpus_census.py`
> → `evals/claims/p1_corpus_census.json`）显示语料 674 题**全是单选 `choice`**、带 (1)(2) 小问结构的只有
> **2 题** ⇒ v1.2–v1.4 记的「多小问 ⇒ `gold_answer` 单元未定义」这个暂停理由**不成立**，据以下述更正替换。
> 真正的阻塞是认识论的：`gen_correctness`/`gen_answerability`/`gen_difficulty` 的 gold 描述的是一道
> **尚未生成**的题 ⇒ 事前无法盲标。项目所有者裁定：
> **Q 为底线**（三项继续 `missing_premise`、Generate 门槛行不发布综合成绩、机械替身只作诊断）+
> **R 可选新增行**（生成后两人**独立求解**、不看模型给的键/解析；属 tier-2 人工证据，永不与 tier-0/1 混写）；
> **P（改 case schema 去迁就可测性）被否决** —— 那是在看过什么能测之后回头改被测主张。
> 另：新增 **P−1 冻结前置条件** = 答案键**可靠性抽查规程**（详见 §4.2 末）。
> v1.4（2026-10-09，收尾修复批）：B7-③ 的单元边界由**两个**改为**三个** —— 全分支横向评审实测
> `cli._update_retrieval_fields`（`reprobe`，零 LLM 路径）是第三条取证路径，既不 reset 也不消费
> `query_failures`，会把原 run 合法升上来的 `error` 降回 `ok`/`empty`。原「两个」的写法在它被接进
> 消费侧之前是对的，现在不再完备 ⇒ 该计数由项目所有者批准的修复批裁定更新（不是实现者自行放宽）。
> v1.3（2026-10-09）：**执行期裁定，两处规格修订**（checkpoint 8，由项目所有者批准，
> **不是**实现者自行纠正代码）：B7-② 的实现前提被实测推翻（异常收敛点在**路由内部**的
> `_safe_to_thread`，探针收不到异常 ⇒ 光让错误发生不足以让 `error` 可达，须由 `run_case`
> **消费 `_query_failures`**）；B7-③ 的第三个 reset 调用点经实测**净降低**故障检测能力
> （一条 query 触发多轮，后轮 reset 抹掉前轮尚未被消费的证据）⇒ **撤销该调用点**，
> reset 只允许发生在独立取证单元的边界。两条的证据与验收见 §5 B7 行与 `EVIDENCE_CHAIN_PLAN.md` Task 8。
> 第二轮同时修正 v1.1 两处事实错误：`gold_review.jsonl` 并非 30 行全空（见 §4.2）；BM25 路由失败对门禁不可见。
> 背景：全仓 review 发现「系统实际表现」与「项目声称已被实验/门禁证明的表现」之间存在断层。
> 关系：**不改写任何冻结件**（`EFFECT_PLAN.md` §3.1/§4、`RETRIEVAL_POLICY.md` 等），
> 只把实现拉回冻结契约，并给契约补上「判定强度」这一维。偏离一律登记，不改原文。

---

## 0. 问题定义

断层不是「没规划」。`EFFECT_PLAN.md` 已写清因果链（§2.B.3）、五项判据（§3.1，v1.0 冻结）、
provenance 100%（§6）。断层的全部来源是这一句：

> **声称的粒度高于被锁定谓词的粒度。**

| 症状 | 实例（本轮已证实） | 机制 |
|---|---|---|
| 失败无法归因 | 15/15 `retrieval_status='ok'` 同时 15/15 `primary_failure='retrieval_miss'` | R2 因果链的机械供给 |
| 成功无法证明 | ④ 归档里 Generate「五项」三项恒 True、一项全 None、一项 ≡ judge 分。★ ⑤ 的复测里 `structure`/`answerability` 已能变红（14/15，#35 抓到 `gen-009` 正文丢失）⇒ **恒真是那份归档的事实，不是判据永远恒真**；但 `correctness ≡ fq≥4` 依旧，且 **#36 的人工手验** 证明它不够：5 道手验里 2 道客观错、1 道满分漏检，`gen-001` 被判 5.0 而 Cache 组号应为 210 写成 46 | R1-A/R1-B + 取证 |
| 语义契约不统一 | `EvidenceDoc.score` 混相似度与 Chroma 距离（top-up 因此反向排序） | R4 字段单一语义 |
| 数据不可证伪 | `rerank_used` 硬写 `True`；门禁守住「开关失真」却漏掉「降级失真」 | R1-A + 状态枚举 |
| 多套现实 | tracked 报告印 `reviewed 66`，数据集 66 条全 `draft`；`docs/README.md:40` 写「129 项」而代码声明值已两度上移（204 → 216，`3e77e01`） | R3 单一来源 |
| **降级伪装成进步** | 把两项标为未测量 ⇒ 复合主指标 0.733 → **1.000**（实测，见 §4.2） | **R5 复合 N/A** |

**非目标（YAGNI）**：不进 CI、不建测试框架、不搞属性测试、不做主张审批流程、
不调检索参数（`EFFECT_PLAN.md:380` 三次负收益先例）、不新增第二套指标实现。

---

## 1. 规则

### 1.1 两套状态，别混

**主张状态**（claim_status，由机器算出，只有三值）：

| 状态 | 判定条件（全部满足才是第一档） |
|---|---|
| **已证明** | R1-A 机械敏感 **且** R1-B 语义映射已签 **且** R2 层级够 **且** 取证时 `code_version`/`prompt_set_version`/`config_hash`/工件 hash 与所引数字一致 |
| **已测量未证明** | 有数，但上述任一缺失 |
| **未测量** | ★ **本行由 checkpoint 10 裁定改写**（v1.0–v1.3 写的是「测不到 / 判据恒真且弄不红 / **gold 前提不存在**」三值触发，比下面那条冻结公式多一条 ⇒ 与 `derive_status` 长期口径不一）：现在只认**两行判据**——**`discriminating=False` 且 `falsify_passed=False`** 同时成立才判「未测量」，即「归档上算不出数」**并且**「mutation 取证也证明不了判据对它声明的契约输入敏感」。唯一真源 = `src/evaluation/task_eval/claims.py` 的 `derive_status()`，本节不再手写第二套条件；「gold 前提不存在」单独出现时落**已测量未证明**（残留代价见下面那条，不许读成已消除） |

> ★ **这一格曾有口径差，收口方式与残留代价（checkpoint 10 裁定，2026-10-10；不是「一直在这么写」）**
> —— 本节 v1.0 起把「gold 前提不存在」直接列为未测量的第三种触发，而 Task 6 冻结在
> `claims.derive_status` 的公式要 `not discriminating and not falsify_passed` 才判未测量。
> 两者在 `gen_correctness` / `gen_answerability` 这一格分岔：mutation 取证的夹具**自带 gold** ⇒
> 判据能被弄红（`falsify_passed=True`），而真实归档 `n_measured=0`（P−1 盲标未做）⇒
> 状态词落成「已测量未证明」而不是「未测量」。
> **裁定 = 改本节措辞去对齐公式，不改 `derive_status`**（公式是三态推导、ledger 与 `--check` 的公共依赖，
> 动它要连带改 tier/债登记，不属文档收尾的范围）。取证命令：
> `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`（三态推导那一组）
> 与 `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --check`（第 3 段 V0 ② 仍拦）。
> ★ **诚实代价如实留在这里，不许读成已消除**：
> ① 读者看到「已测量未证明」配「已测 n=0」这一对时**仍然反直觉** —— 状态词说的是「判据有没有牙齿」，
> 数值列说的是「归档里有没有数」，两者本来就在问不同的问题，但并排印出来就像矛盾；
> ② `evals/claims/ledger.md` 判据级附表那条 ★ 注记**保留**（它给的是依据：冻结公式 + mutation 测的是
> **判据对契约输入的敏感性、不是主张的数值**），★ 但它是 `scripts/build_claim_ledger.py` 的渲染产出、
> 本 Task 不改代码 ⇒ 注记里「与 §1.1 口径不一致 / 待 Task 10 文档收口」那半句在收口后要读作
> **历史指向**（现行判据以本节为准）；把注记文本一起刷新需要一次动 `scripts/` 的小改；
> ③ 这一格**不因此变成「已证明」**，也不免除 V0 ② 对「required 判据全未测量」的拦截。

**工件状态**（artifact_status，历史数据用，不改写数值）：`active` / `superseded` / `invalidated`，
`superseded` 必须带 `superseded_by` + `reason`（如 `predicate_semantics_changed`）。
⇒ 回答「为什么 phase0 的 0.7333 还在仓库里」这句话，靠字段而不是靠记忆。

文档不允许出现第三种主张状态措辞。

### 1.2 R1 拆两层：牙齿 ≠ 咬对东西

- **R1-A 机械敏感性**：注入 mutation ⇒ 判据按预期变红；且**恰好这一条变红，其余不动**。
- **R1-B 语义有效性**：每个判据声明它实现的是冻结契约里的哪个谓词，以及**该谓词点名的输入字段**：

```python
{
  "name": "gen_structure",
  "tier": 1,
  "contract_ref": "EFFECT_PLAN.md §3.1 completeness_pass",
  "contract_inputs": ["stem", "options_or_requirement", "answer_key", "analysis"],  # 契约点名的
  "fn": ...,
  "falsifier": "逐字段删除：删任一 contract_input ⇒ 必须变 False",
}
```

R1-A 的检查升级为**覆盖性检查**：`mutation 集 ⊇ contract_inputs`。
只删代码碰巧读的那个字段不算通过（`return bool(record["analysis"])` 能骗过单点 mutation，
但骗不过「四个契约输入各删一次都必须变红」）。

★ **R1-B 的诚实边界**：`contract_ref` 与覆盖性检查让映射**可审计**，不自动**证明**它语义正确——
最终仍需一次人工对着冻结定义签字（每个判据一次，不是每轮实验一次）。本方案不把它写成「已闭合」，
写成「已审待签 / 已签@版本」。这条自己也要守本文件的规矩，否则方案本身就在过度声称。

### 1.3 R2 证据分层 + 单项四态

| tier | 含义 | 例 |
|---|---|---|
| 0 | 机械事实，不经模型 | `retrieval_status`、`rerank_status`、`memory_read_status`、`tool_error`、episode 是否真落 Store |
| 1 | 可观测物证（对产物做结构/一致性检查） | 四件套齐全、答案键 ∈ 选项集、解析结论与答案键同结论 |
| 2 | judge 的观点 | `final_quality`、`answerable`、`failure_reason` |

**每个判据项返回四态，不是两态**：`pass` / `fail` / `not_applicable`（本 case 按契约就不适用）/
`missing_premise`（契约要求它，但 gold 或证据不存在）。后两者都记 `None`，但**必须带 reason**，
因为它们在 R5 里的待遇相反。

两条硬规则：
- 门槛行的质量分允许 tier 2（`EFFECT_PLAN.md:334` 的 QA 门槛本就是 `final_quality≥4`，不动它），
  但须满足两个前置：① 重复测量抖动已量化（§21 已有三次抖动数据）；② **判据边界已校准**。
  当前做不到：`calibration_30.jsonl` 的 `human_score` 分布 = **5×28 / 2×1 / 0×1**，
  而每条门槛都在 `≥4` 翻转 ⇒ 边界档（3、4）**零样本**，「judge 在门槛附近是否与人工一致」从未被测。
  缺任一前置 ⇒ 该行 = **已测量未证明**。
- **因果链每一环由更低 tier 支撑**：`retrieval_miss` 仅在 tier-0 显示检索确实返空/失败时允许写入；
  judge 给的原因一律落到 `judge_failure_reasons`（诊断位，不参与 `primary_failure`）。
  这是 `judge.py:296` 已有 `judge_memory_*` 隔离模式的推广。

### 1.4 R3 禁止的是「孤立结论」，不是结论句

规则对象是**可验证事实断言**：一个数字或一句「通过/一致/为空」若没有 `证据锚点 + 复现命令`，
即视为孤立。带来源的结论句合法，文档照常可读：

```
本次实验通过全部门禁。
证据：evals/claims/ledger.md#gate-2026-10-08
复现：PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --check
```

检查器只对「含数字或「全绿/应为空/逐位相同/一致」且 100 字符内无 `证据：`/`复现：`/反引号命令」的行报 warning。
本轮实例：`EXPERIMENTS.md:908` 断言某 diff 为空，实测 **9 文件 +801/−8**。

### 1.5 R4 检索字段单一语义

`EvidenceDoc.score` 只能是**相似度**（越高越好）。RRF 融合分另存 `rrf_score`；
Chroma 距离在进入契约前经**唯一**换算函数转换。实现第一步先测各 collection 的 distance function
（cosine → `1-d`；l2 → `1/(1+d)`），换算只允许存在于 `src/rag/embeddings.py` 一处。

### 1.6 R5 复合指标的 N/A 语义与分母（本方案的关键新增）

每个判据项返回四态（§1.3），复合时区分**谁有权缺席**。规格表因此多一个字段：

```python
"required_when": ...   # 例：difficulty_match 仅当 query 指定难度才必需；
                       #     correctness / answerability 对任何生成题恒必需
```

**合取型复合指标**（`five_of_five` 这类「全部必需项都过才算过」）：

```
COMPOSITE = 所有 required 项都已测 ? evaluate(合取) : MISSING_PREMISE
```

而不是 `all(x is True or x is None)`。逐成分对照：

| 成分状态 | 复合结果 |
|---|---|
| 全 `pass` | `pass` |
| 任一 `fail` | `fail` |
| 任一 required 项 `missing_premise` | **`missing_premise`（不是 pass）** |
| 仅 `not_applicable` 与 `pass` 混合 | `pass`（契约不要求的项可以不参与） |

**分母语义（v1.2 明确）**——这是「10/10=100%」还是「10/15=66.7%」还是「N/A」的问题，必须有答案：

| 报告位 | 规则 |
|---|---|
| **主指标**（进 §6 门槛行的那一个数） | 任一 required 项 `missing_premise` ⇒ **整条主指标 = `missing_premise`（N/A）**，**不出百分数** |
| **辅助位**（诊断，明确标注为辅助） | 允许 `measured_n` / `missing_n` / `measured_pass_rate` 三个数并列，如 `measured_n=10, missing_n=5, measured_pass_rate=1.000（辅助）` |
| **单项率** | `not_applicable` 与 `missing_premise` 都出分母（对齐规则①②），但**必须并列 `n_a` 与 `missing_premise` 两个计数**，不得合并成一个 `n/a` |
| **族级零覆盖** | 某项在本族**全部** case 上都 `not_applicable`（如实测 `gen_difficulty` 15/15，因 query 未指定难度）⇒ 该族对这个维度**零覆盖**，必须在文档显式披露，不能只写「N/A」 |

现状 `metrics.py:440-443` 把 `None` 一律剔除，不区分后两行 —— 这正是 §4.2 事故的来源。
`not_applicable` 与 `missing_premise` 必须是不同值，否则「无 gold」会被洗成「全过」。
★ 辅助位永远不允许变成论文里的那个「正确率」——`build_claim_ledger` 只把主指标写入 §6 行。

---

## 2. 单元与接口

**先定 schema，再写判据**（第一轮 ⑨）：`predicates` 只能读 Evidence Record，缺字段是 V0 红灯，
不允许在写判据的过程中回头改 `runner.py` 补字段。

```
schema/evidence_record.py   ← P0.1 事实层唯一定义（含 provenance）
predicates/
  ├── registry.py   ← P0.2 tier 表 + 规格表 + contract_inputs（唯一注册）
  ├── common.py     ← rate / every_item_passes(R5 版) / degenerate 检查
  ├── generate.py   ← P0.3 各 predicate + falsifier
  ├── verify.py
  └── memory.py
falsify.py          ← P0.4 跑 mutation 矩阵，校验「恰好变红」+ contract_inputs 覆盖
build_claim_ledger.py → evals/claims/ledger.md（生成物）
```

`metrics.py`(672)/`report.py`(435) 改为**只读 registry**，删掉各自的本地公式副本 ——
否则拆包反而造出第二个真源。拆包同时把 12 个超 600 行文件的问题往前推一步
（`CLAUDE.md:88` 红线），目的不是好看，是「一个指标只有一处定义」。

---

## 3. 数据流与 provenance（第一轮 ⑥）

```
run → archive.jsonl（Evidence Record + provenance）
        ↓ 零 token
reanalyse（按 registry 重算：四态、R5 复合、恒真项质询）
        ↓ 零 token
falsify（每条主张弄坏一次 → 记录是否恰好变红 + 覆盖 contract_inputs）
        ↓ 零 token
ledger（三态 + artifact_status）
        ↓
docs（只嵌 ledger 锚点 + 复现命令）
```

provenance 字段（现状只有 `code_version`/`golden_sha256`/`date`，`docs/README.md:64` 已如实承认缺 `argv`）：

| 新增 | 内容 | 为什么 |
|---|---|---|
| `model_refs` | agent 与 judge 的 `<gateway>:<model_id>` | 「同代码同提示但换模型」目前不可见 |
| `sampling` | judge/agent 的 `temperature`（+ 若有 `top_p`） | judge 无 seed，温度即结论 |
| `experiment_config_hash` | 非密钥白名单字段（k/阈值/`RERANK_ENABLED`/`USE_FAKE_EMBEDDING`/缓存开关）的排序后 hash | `.env` 改了要能被看出来；**只 hash，不落原值**（对齐既有 #29「settings 泄漏」修复） |
| `dependency_lock_hash` | `uv.lock` sha256 | 依赖漂移 |
| `argv` + `script` | 与检索类归档同款 | 效果数字也能反查到命令行 |

★ 一致性要求：`已证明` 的取证记录必须与所引数字**这五项全一致**，否则状态自动降级。
★ `reprobe` 的既有缺陷顺带修掉：`cli.py:260-279` 用新检索覆盖指标却把 provenance 留在旧值
（旧输入新输出）——**覆盖任何指标字段时 provenance 必须同写，否则拒绝写入**。

---

## 4. 归因改写（含改名，第一轮 ②③ + 第二轮 1、7）

### 4.1 原则

**证据不是等价定义，就不沿用原指标名。** 冻结的 `gen_correctness` / `gen_answerability` 名字保留、
状态改为 `missing_premise`（未测量）；机械可算的部分另起名字，且明示它是**必要非充分**条件。

| 新指标（tier 1，机械） | 它证明 | 它不证明 |
|---|---|---|
| `gen_answer_key_validity` | 答案键存在 ∧ ∈ 选项集 ∧ 正确项唯一 | 这题「可被作答判定」（原 answerability） |
| `gen_analysis_agreement` | 解析结论与答案键同结论（#33 产品规则的评测化） | 答案本身对不对（原 correctness） |

**★ 与 #36 的关系（必须说清，否则像在推翻已定决策）**：#36 的处置是
「登记为判据局限、**不改判据**（§3.1 v1.0 已冻结）」。本方案**同意不改 §3.1** —— 因为 §3.1 的原文写的是
`correctness_pass = gold 判定正确`，**它要求的正是 gold**；现在的实现 `fq≥4` 不是这条冻结判据的实现，
而是它的替代读数。所以 P−1 补 gold 是**把实现拉回冻结文本**，不是改判据。
#36 顺带列出的两条低成本改进（judge 先重算再判 / 抽一批人工复核表）与 P−1 是同一件事的两个入口，
其中「人工复核表」正是 §4.2 的盲标规程。

### 4.2 已实测的后果，与「补 gold」升级为 P0 前置

把 `gen_correctness`/`gen_answerability` 标为 `missing_premise` 后，按现有 `every_item_passes`
（`None` 出合取）实测：**`gen_case_pass` 从 0.733 变成 1.000，n 仍为 15、n_a 仍为 0**。
即「诚实标记测不到」被复合逻辑翻译成「全过」。所以 §4.1 的改名**必须**和 R5 同批落地，
否则本方案自己制造一次新的断层。R5 落地后：该批 Generate 主指标 = **`missing_premise`（整族不可出数）**。

**★ ⑤ 的复测读数（`EXPERIMENTS.md` §22.1）同样不能沿用**：锚点 ⑤ 上 generate-only 复测已把主指标抬到
**13/15 = 0.867，过了 ≥0.75 的门槛**（`final_quality` 均值 3.933→4.400，回归 0 条）。
但那 13/15 依然是 `correctness ≡ fq≥4` 的合取，而 `gold_answer` 仍 0/15 未填 ⇒
**R5 一落地，这个「过线」读数会变成 `missing_premise`**（不是 fail，也不是继续 0.867）。
⇒ 处置：该归档标 `artifact_status=superseded`，`reason=composite_na_semantics_changed`；
论文里若要写 0.867，必须连着 #36 那句「judge 不重算算术，它测的是像不像一份能用的答案」一起写。
这也是 P−1 排在最前面的实证理由：**补了 gold，0.867 这类数才重新有据；不补，它只能降为 limitation。**

**★ 更正 v1.1 的一处事实错误**：我曾写「`gold_review.jsonl` 30 行全 `None`」——只看了前 3 行。
实测底数是：该表 30 行 = **generate 15 + grade 15**；`review_fields` 有三个键
（`gold_answer` / `expected_difficulty` / `human_score`）；其中
**generate 的 `gold_answer` 与 `expected_difficulty` 各 0/15 已填**，
**grade 的 `human_score` 已 15/15 填满，分布 `{100.0: 8, 0.0: 7}`**。
后一半正是 `metrics.py:450` docstring 里描述的**两极退化 gold**（独立核对吻合）。
⇒ 待补工作量比我原先估的小一半，但暴露出**第二个**缺口 —— 事后证明那不是缺口而是指标本身的前提不成立（见下面 G1b 已撤回）。

| 项 | 内容 | 状态 | 成本 |
|---|---|---|---|
| **G1a** | 填 generate 15 行的 `gold_answer` + `expected_difficulty` ⇒ `gen_correctness`、`gen_answerability`、`gen_difficulty` 三项从 `missing_premise` 变可测 | **P0 前置：不补 ⇒ Generate 五项主指标无定义域，禁止出现在正式效果章** | 零 token，15 行 × 2 字段 ≈ **2 人时** |
| **G1b（已撤回，2026-10-08 checkpoint 2）** | 原要求「补非两极 `human_score`」，好让 `score_tolerance@±10` 有中间地带可判别 | **前提不成立**：`gold_sanity` 的集合级 PENDING 声明 L3 语料 674/674 全是 2 分选择题、case 作答仅 1 个字母 ⇒ **无部分分可标**。为满足原指标硬造中间档就是造标签 | 改为 **`verdict_agreement` 作 Grade 行级判据 + 两极 gold 显式披露**（`metrics.py:475` 已实现、报告已自动输出）。属**偏离登记**，不改写冻结件 `EFFECT_PLAN.md` §3.1 |
| **G2** | 只披露：主指标标「未测量」并登记 §20.7，机械两项作辅助呈现 | **降级方案**（不是平行选项） | 零成本，效果章少两行能拍胸脯的数 |

规则写成一句：**只有当 §6 门槛行愿意改标「未测量」时，G1 才可以不做。** 若效果章要保留
Generate 的百分数，G1a 就是正式实验的前置条件，排在 P0 之前。
Grade 不再要求补标 —— 它的两极 gold 是语料性质决定的，改用 `verdict_agreement` 承担行级判据
（见上面 G1b 已撤回一行），并把「gold 仅两极」作为已知偏离披露。

**★ 盲标规程（防止「自标自证」）**：gold 必须是外部事实，不能从模型输出反推。
`model_answer → gold → correctness` 等于自己给自己出答案。

1. 标注**只读** `demo/generate_cases.jsonl` 的题面 + 选项 + KB 依据；
   `gold_review.jsonl` 本身不含 `system_output` 列（已核实），但同 case_id 的 `calibration_30.jsonl`
   （含 `system_output`，与 gold_review 的 case_id 重合 20 个）**在标注阶段不得打开**。
2. `review_fields` 增一个**必填** `gold_source_ref`，指向 KB 的 section/kp 出处——
   无出处的 gold 视为未填（V0 检查它）。
3. 先标后比：`gold_answer` 定稿后才允许与归档的模型答案对照。
4. 一条告警（非自动失败）：若 `gold_answer` 与归档模型答案键一致率 = 100%，
   触发「疑似反推」提示，需人工说明依据。

### 4.3 其余归因行

| 主张 | 现状 | 改为 |
|---|---|---|
| `gen_structure` | schema 能解析即 True（15/15） | 按 §3.1 `completeness_pass` 查四件套**逐一非空**；`contract_inputs` = 四个组件，四个 mutation 各必须变红 |
| `gen_coverage` | 15/15 True（#27 之后） | 保留 + R1-A 质询（抹掉任一 `knowledge_points` 必须变红，否则坐实判据没吃 KP） |
| Verify 归因 | 同一归档 15/15 `retrieval_status=ok` **且** 15/15 `pack_nonempty=True`，而 `primary_failure=retrieval_miss`×15 | `metrics.py:47-60` 优先级不动，但 `retrieval_miss` 改由 tier-0 门供给；judge 原因落 `judge_failure_reasons`。★ 机械路径（`judge.py:375-376` 要求 `not pack_nonempty`）在这里没触发 ⇒ 那 15 条只能来自 judge |
| Memory 三维 | 读链故障与「没有卡」同为 `""`（`teaching_graph.py:44-46`→`memory_scorer.py:164-166`） | 见 §5 B4 的四态 `memory_read_status` |
| Grade `score_tolerance` | `degenerate_gold` 已披露（做法正确） | 泛化为 R1-A 的一个实例，无新逻辑 |

---

### 4.4 P−1 冻结规程（v1.6：答案形态 / 答案状态 / 扩查升级 / R 行）

★ **两条正交维度，不许合并**：`gold_answer_form` 说「答案长什么样」，`answer_status` 说「来源与可用性如何」。
一道题可以形态合法（单个大写字母）却因缺图、原题歧义或扫描不可辨认而**不能用作 gold**。

#### 4.4.1 `gold_answer_form`（答案形态）

| 值 | 状态 | 冻结要求 |
|---|---|---|
| `single_choice` | **批准，语料正式使用** | 规范化后**必须恰好一个** A–H 大写字母；多字母**不得静默取首个**（`metrics.answer_keys_of` 保留重复、不取首，正是为了暴露这件事） |
| `multi_choice` | 留位 | 字母集合升序去重；须显式声明「全选对才正确」的判定语义；**暂不纳入现有 claim** |
| `numeric` | 留位 | 必含 数值 + **单位** + 容差；缺单位即不可比较（不得默认同单位） |
| `text` | 留位 | 规范化文本 + `aliases[]`；语义判等需人工 ⇒ 属 tier-2，**不得伪装成机械精确匹配** |
| `steps` | **批准用于 R 行的结构表达** | 父题 ↔ `part_id[]` 关联；每 part 独立记录判定与状态；父题级汇总规则见 §4.4.4 |

#### 4.4.2 `answer_status`（来源与可用性）

| 值 | 冻结含义 | 处理原则 |
|---|---|---|
| `present` | 答案键经核验，与原题及选项一致 | 可进入正确率评测前提 |
| `missing_key` | 来源**没有**答案键（语料 160 题：`gap_fields=[answer]`152 + `[answer,figure]`8） | 记入缺键统计，**不入正确率分母**；**禁止**模型补答案、按考点猜答、或把「参考解析为空」解释成已验证 |
| `incomplete_source` | 缺图等来源缺陷致题面不完整（语料 42 题） | 与缺键**分开统计**；不得直接视作错键 |
| `illegible` | 原始扫描材料无法可靠辨认（核验时人工判定） | 单独披露为不可用；**不算已确认错键**，也**不算通过核验** |
| `undecidable` | 题本身歧义/多解等致答案无法唯一确定 | 作为**对象本身的性质**记录，不得与证据不足混为一谈 |

★ **三条必须守住的边界**：① `undecidable ≠ missing_premise`（前者是题目不可唯一判定，后者是我方证据不足）；
② `missing_key ≠ incomplete_source`；③ `illegible ≠ 错键`。
★ **实现约束**：`answer_status` 描述来源及其可用性，**不直接等同** §1.3 的四态 verdict；映射见 §4.4.3（第 3 步冻结）。
一个状态**不得被无条件映射成 pass**。

#### 4.4.3 四态映射（★ 待第 3 步裁定，本节先留空位不许猜）
（留待项目所有者裁：`answer_status` × 证据充分性 → `pass/fail/not_applicable/missing_premise`。）

#### 4.4.4 父题 / part 汇总规则（★ 待第 3 步裁定）
★ 已定的一点：**不得复用 §1.6 R5 的复合规则**做 part 汇总 —— R5 里「pass 与 not_applicable 混合算 pass」
是为「同一题上多个判据」设计的；若照搬到 part 级，一道含不可判定小问的题会被算成通过，
正是 §4.4.2 那条边界想禁止的事。part 级规则须单独冻结。

#### 4.4.5 发现错键后的扩查与升级（★ 已冻结为规则；未冻结前不得临场决定）
1. **发现错键即停止使用「键可靠」结论**：先记录已确认错误及其来源，**不得**以其他抽中题正确来抵消。
2. **出错层降级为「来源可靠性未证」**：该层其余未抽查题不得继续沿用无条件可靠假设。
3. **执行扩查**：出错层追加至该层有键题的 **50%**（不足则全查）**且**对同来源相邻批次追加 **≥10 题**。
   ★ 这个 50% 是**扩查目标**，不是「抽到一半没发现新错就自动证明可靠」的标准。
4. **纠正保留完整血缘**：原记录标 `superseded` 并经 `superseded_by` 指向纠正后记录；
   **不得覆盖原始值、抹掉原始 OCR 结果或删除错误证据**（沿用 §1.1 `artifact_status` 语义）。
5. **扩查后再现错键 ⇒ 暂停该来源链作为 gold 出处**：在完成独立校勘与重新审核前，相关 claim 回落为
   limitation，不得继续用它支撑「已证明」。

★ **统计口径的三分法（必须分开写，不许互相顶替）**：
① **抽样设计目标** —— 零接受属性抽样：真实错键率 ≥5% 时以 ≥95% 概率至少发现一个（n=59）。
② **实际审计结果** —— 抽了哪些题、发现几个错键、哪些层是全查。
③ **最终可支持的结论** —— 按**实际**设计与结果界定到总体还是具体来源层。
★ 因强制分层配额存在，**不能把简单随机抽样的发现概率直接当作分层后的无条件总体置信结论**。
2016 年 5/5 属**该层全查** ⇒ 对该层这 5 道有键题无抽样误差；但它**不能自动证明其他年份批次可靠**。
发现错键必须按上面五步升级，**不得只报整体平均值**。

#### 4.4.6 R 行：独立人类证据（★ 批准启用，≈2–3 人时）
R 必须与 Q 的自动化基线**分开记录**，且拆成三问、**不得合成一个笼统的「人类判对率」**：
① **答案正确性**：独立求解所得答案是否与生成题的正确答案一致；
② **可判定性**：题面是否足以让独立求解者得到确定答案；
③ **难度**：是否有**独立且预先冻结**的判定标准。
两名标注者先**独立作答且看不到模型答案与解析**，随后记录分歧、裁决结果与不可判定原因；
含小问的题按 §4.4.1 `steps` 的父题 + `part_id` 规则逐项记录。
★ **两条红线**：R **不得**回填成机器原本缺失的 gold，也**不得**把 `gen_correctness` / `gen_answerability` /
`gen_difficulty` 自动升级为「已证明」；若要宣称 R 行本身达 tier-2「已证明」，还须完成**重复运行抖动分析 +
阈值校准 + 相应证据记录** —— 两人独立作答是**必要设计，不是充分证明**（§1.3 R2 门槛行前置）。

## 5. 业务链修复清单（二分）

裁决：**B1（top-up 语义与排序）现在修并接受重录基线；BM25 IDF 与 `k=5` 语义延后。**
二分的目的很具体：防止执行的人把它读成「B1 修了 ⇒ 业务侧已经全修完」。

### 5.A P0 Runtime Correctness —— **不修就禁止正式实验**（证据链本身会失真）

★ 执行顺序上 **B7 必须与 §4.3 的归因门同批、且先于它**（生产者先于消费者）；且 B7 的「生产者」按 v1.3 含**两侧**——路由侧记录失败、评测侧消费失败 —— 只修前者等于没修。归因门要读
`retrieval_status == "error"`，而 B7 之前这个值不可达。详见 `EVIDENCE_CHAIN_PLAN.md` 的依赖矩阵。

| # | 位置 | 改法 | 数字影响 |
|---|---|---|---|
| B1 | `rag/layer_recall.py:128-131` + `evidence_policy.py:138` | R4 语义统一后排序方向自然转正 | **会变**（top-up 选中的文档变了）→ 重录受影响路由 + 差异登记 §20.7 |
| B2 | `rag/pipeline.py:593` | ★ 不再只给布尔。新增 tier-0 枚举 **`rerank_status`**：`off` / `success` / `degraded`（调用成功但无分或空结果，回落原序）/ `failed`（抛错或超时走 `default`）。`rerank_used` 降级为**派生字段**：仅 `success ⇒ True`，其余全 `False`。派生条件判 **metadata 含 `rerank_score` 键**（`reranker.py:246` 有合法写 `0.0` 的路径，用真值判断会把假重排 `on` 路由误翻成 False，等于借修诚实度换基线）。★ `rerank_status` 要**落进 record**（含 `run --no-agent` 的检索探针归档），不能只进遥测 | **不变**（`RERANK_ENABLED=false` 时走 `:565-570` 已返回 False；`on` 路由 `_fake_rerank` 确实写分）。⇒ 消融从此能区分「重排关」与「重排开但坏了」 |
| B4 | `agents/teaching_graph.py:44-46` + `memory/safe.py` | 新增 tier-0 **`memory_read_status`** 四值 + 映射：<br>`not_attempted`（`uid is None`，`:43` 那条分支就是它，今天被压成 `""`）→ 三维 `None`<br>`success` + 命中期望值 → `recalled=True`；`success` 未命中 → `recalled=False`<br>`empty`（读成功但无卡）→ `recalled=False`<br>`failed`（超时/异常）→ 三维 `None`<br>⇒ 「这个 0.5 是不是 Store 挂了」变成**有证据可答**的问题 | 只影响今后归档；已归档 Memory 数标 `superseded`，新状态待重跑 |
| B7 | `rag/bm25.py:54-59`、`rag/vectorstore.py:142,340`、`evaluation/retrieval_gate.py:1262`、`retrieval_probe.py:111,140,149` | **检索失败必须传播**：BM25 取 collection 失败时 `return []` 且**不写 `_query_failures`**（向量路径 `:340` 会写），门禁的 `unexpected_query_failures` 看不见它。★ 更深一层的后果是**归因被污染**：探针的契约是「异常收敛为 `status="error"`」，而咽掉的异常让探针看到「查到空」⇒ 写成 `empty`，于是 `error` **今天不可达**，归因层没有「路由坏了」这个证据可用。改法：① 失败计入 `_query_failures`；② 让 `retrieval_status` 真的能取到既有的 `error`（**不发明新枚举名** `route_error`：`judge.py:373` 已在比较 `== "error"`，改名会打断这条既有判定）。★ **v1.3 更正实现方式**：原设想「让异常真的抛出，探针既有契约自会收敛为 `error`」经实测**不成立** —— 收敛发生在 `_safe_to_thread`（`routes.py:257-275`，按路由逐个收敛）而**不在探针层**，抛出的异常到不了 `retrieval_probe` ⇒ 探针仍写 `ok`/`empty`。正确做法是让**消费侧**接上 tier-0 证据：`run_case` 在探针返回后读 `query_failures`，非空即把 `retrieval_status` 升为 `error`（只升级不降级）并据此关闭检索层归因门；失败清单同时落成**只作凭据、不进任何比率分子分母**的诊断字段。★ 实测 27 份 task_eval 归档 / 367 条记录里 `error` **出现 0 次**（`ok`×309、`empty`×34、24 条键缺失）——它只是 `retrieval_probe.py:66` 的代码默认值，那条分支从未被触发过；这正是「坏了被说成没查到」的实证，也是 Task 8 归因门必须为 `error` 自带取证的原因。③ `_query_failures` 可清零，但 **reset 只允许发生在独立取证单元的边界**：`retrieval_gate` 每条 query 前、`task_eval.runner.run_case` 每次探针前、
   `task_eval.cli._update_retrieval_fields`（`reprobe`）每条 record 前 —— 共**三个**单元边界调用点
   （★ v1.4 追加第三个：收尾修复批 Important-1 实测 `reprobe` 是第三条取证路径，原写「两个」时它绕过了消费侧）。★ **v1.3 撤销**原列的第三点（`_amulti_route_search` 每轮开头）：一条 query 在 `pipeline.py:448/466/672` 会触发多轮（HyDE 恰在「第一轮空/差」之后才跑），后一轮的 reset 会抹掉前一轮**尚未被 `run_case` 消费**的失败证据 ⇒ 实测（注入 BM25 全线故障）失败记录从产生时的非空到读取时为 `[]`，检测能力**低于改动前**（旧实现永不 reset，读取时至少能看到实时列表）。失败证据必须保留到被消费之后才清 | 基线数字预期不变（BM25 今天跑得通）；修的是「坏消息看不见」+「坏了被说成没查到」 |

### 5.B P1 Product Correctness —— **不修可以正式实验，但必须登记 limitation**

BM25 IDF 用截断候选池（`bm25.py:84,98-99`）、`k=5` 被当未指定（`retriever.py:186`、`pipeline.py:294`）、
`_rrf_scale_needed` 硬编码复刻阈值公式（`postprocess.py:89-97`）、parent-window 文本重复
（`splitter.py:229`+`postprocess.py:685`）、`weak_topics` 清除死分支（`weak_topics.py:91-93`）、
生产/评测聚合口径不一致（`:102`）、`difficulty="mixed"` 与子项 `Literal` 冲突（`questions.py:50` vs `:17,24`）、
`score` 越界不 clamp 而抛错（`grading.py:22`+`grading_core.py:29-30`）、`is_wrong`/`score` 不一致、
B3 空召回写缓存、B5 `/api/metrics` 鉴权与阻塞、B6 SSE 断连收尾。

★ **两条要特别盯**：`difficulty=mixed` 与 `score` 越界都会让整单失败并**计入 §6 的 `tool error <5%` 门槛行**。
⇒ 若正式实验那一行因此不达，这两条**自动从 5.B 升级到 5.A**（阻塞重跑），不能只登记 limitation。

### 5.C 只欠改口（今天连产品行为都不是）

`lightweight_rerank` 零消费方、`HYDE_RERANK_SCORE_THRESHOLD`
读方条件不可达（`hyde.py:35`）、`_raw_search` 抖动修复对向量路由是死代码（`routes.py:333`，
而 `kp_hit_flip_diag.py:95` 正 patch 在这个不可达函数上）、记忆卡语义锚点（`working.py:56,82` 与
`memory_step2_gate.py:180` 断言的不是同一件事）、question↔grade 闭环（`ref_episode_id` 无写入方，
`store.db` 中 0/58 条批改带 `batch_id`）。

---

## 6. 反向取证矩阵（mutation 必须覆盖 contract_inputs）

| 主张 | 弄坏动作（record 层） | 期望 |
|---|---|---|
| `gen_structure` | **逐个**删 `stem` / `options` / `answer_key` / `analysis` | 四次都必须变红；只删得出一次 = 判据其实只读一个字段 ⇒ R1-A 不过 |
| `gen_answer_key_validity` | 键改成 ∉ 选项集 / 制造两个正确项 | 各自变红 |
| `gen_analysis_agreement` | 解析结论改成与键相反的选项 | 变红，且 `final_quality` 不动（证明与 judge 解耦） |
| `gen_coverage` | 抹掉一条 `knowledge_points` | 变红 |
| Verify 归因 | 把 `retrieval_status` 改 `empty` | `primary_failure` 才允许 `retrieval_miss`；反向（ok 却报 miss）必须被拒 |
| Memory 三维 | 分别注入 `not_attempted` / `empty` / `failed` | 前→`None`、后两者→`False`/`None` 按 §5 B4 表；`failed` 绝不得出 `False` |
| `rerank_status` | 注入无分降级 | `status=degraded` 且派生 `rerank_used=False`；若仍 True ⇒ B2 未生效 |
| R5 复合 | 任一成分设 `missing_premise` | 复合 = `missing_premise`，**不得**为 `pass`（这就是 §4.2 事故的回归测试） |
| 三态推导 | 把取证 `config_hash` 改成旧值 | 状态从「已证明」自动降级 |

---

## 7. 文档承载

- **冻结件不动**；实现与冻结口径不一致 → 偏离登记进 `EXPERIMENTS.md` §20.7，不改原文。
  本方案新增**五处**待登记偏离：① §3.1 五项中 `correctness`/`answerability`/`difficulty` 三项在无 gold 时为
  `missing_premise`（走 G2 时）；② Grade gold 为两极 `{100:8, 0:7}`，判别域受限 → 行级判据改用
  `verdict_agreement`；③ R5 改变了复合指标的聚合语义（旧归档按新规则重算会得到不同状态词）；
  ④ 5.B 全部延后项的 limitation 清单；⑤ **corpus 结构偏离**：Task 3 标定实测 generate 产物
  14/15 为多小问混合卷（综合应用+选择+填空），「一题一答案行」的机械解析前提不成立 ⇒
  机械 answer-key 判据降级为「纯选择题诊断器」（checkpoint 3 裁定 C，边界见
  `EVIDENCE_CHAIN_PLAN.md` 前置节）。★ v1.5 更正：Generate 的 P−1 暂停理由**不是**「gold schema 未定义
  （多小问）」—— 普查显示语料全是单选题；真实原因是那三项的 gold 指向尚未生成的题（见版本头 v1.5）。
  这是**语料/契约披露**，不是「实现错误因此重写产品」。
- **活文档勘误**（4 处；★ 一律**改成命令**而不是写死数字 —— 本文件自己就先被这条打过：
  写「16 份 / 27 份 / 204 项」时，`3e77e01` 已经把护栏抬到 216、把跟踪清单变成 17 份）：

  | 位置 | 过期声称 | 改成 |
  |---|---|---|
  | `docs/README.md:3` | 「标签待打」 | `git tag -l 'V-*' --format='%(refname:short) -> %(objectname:short)'` |
  | `docs/README.md:40` | 「现 129 项」 | `grep -n "^_EXPECTED_ITEMS" scripts/memory_step4fix_gate.py` 的生成值 |
  | `docs/README.md:73` | 「`git ls-files` = 0」 | `git ls-files evals/results/task_eval \| wc -l` 与 `git status --short -- evals/results/task_eval \| grep -c '^??'` 两条并列（前者已跟踪的仍是 `.md`，后者是数值工件） |
  | `CLAUDE.md:47` / `README.md:144` | `--dataset evals/sample_408.jsonl` | 实为 `evals/datasets/golden/sample_408.jsonl`（`src/evaluation/cli.py` 的默认值） |

- **数值工件纳入版本控制**：以 `git status --short -- evals/results/task_eval` 的 `??` 计数为准
  （本轮两次实测分别是 27 与 41 —— 数字会漂，命令不会）。「冻结、只读」在没有版本控制前只是措辞；
  跟踪后配合 `artifact_status`，旧数字留档而不冒充当前结论。
- `docs/README.md` 加一行指向生成的 `evals/claims/ledger.md`。

---

## 8. 验证与退出准则

| 步 | 内容 | 判据 |
|---|---|---|
| **V0** | **Evidence Record schema 完整性 + 未测量 predicate 拦截**（阻塞 P4） | ① 每条 `已证明` 主张所依赖的 tier-0/1 字段，**在归档里键真实存在**（键存在，非真值）。禁止 `.get(k, False)` / `.get(k, 0)` 掩盖缺字段（AST 检查，沿用 step4fix gate 已有的 AST 手法）；`gold_source_ref` 缺失的 gold 视为未填。② ★ **正式实验禁止依赖未测量 predicate**：`claim → required predicates → 任一 missing_premise ⇒ claim = unmeasurable ⇒ 禁止进入正式效果章的门槛行`。这条就是 §4.2 里「`gen_case_pass = 1.000` 而 correctness/answerability/difficulty 全 missing」的机械拦网，也是 G1a 排在 P0 之前的原因 |
| V1 | 按 registry 重算（`reanalyse`，零 token） | 每项带 tier + 四态 + reason；无恒真项被当门槛证据 |
| V2 | `task_eval sanity` | ERROR 0（现有护栏不变） |
| V3 | `falsify` 全矩阵 | 每条主张「恰好它变红」；且 mutation 覆盖其 `contract_inputs` 全集；红不了的自动降级并在 ledger 可见 |
| V4 | `build_claim_ledger` | §6 每行有状态词 + R1-B 签署状态；`已证明` 行数 = 论文可引用行数 |
| V5 | `retrieval_gate`（B1 后 6 条路由逐条）+ `probe_gate` | 基线重录 + 差异登记 §20.7；禁止静默 `--update-baseline` |
| V6 | `ruff check/format --check src/` + `pyrefly check` | 现状全绿（本轮实测：ruff 通过、130 文件已格式化、pyrefly 0 errors / 13 suppressed / 65 warnings） |

★ **V0 的阻塞范围要划清**（否则方案会把自己锁死在截止日期前）：

- **阻塞**：把 `missing_premise` 的族写进 §6 门槛行；把无鉴别力的行标成 `已证明`；5.A 或 V0 未过时进 P4 正式重跑。
- **不阻塞**：把某族明确披露为「未测量 + 原因 + 补救路线」。这类行可以出现在论文里，
  但只能以 **limitation** 的身份出现，不能以**成绩**的身份出现。
- ⇒ 落地成一句可执行的话：**Generate 门槛行要么补 gold（G1a，零 token，约 2 人时），
  要么整族降为 limitation；Grade 的行级判据改用 `verdict_agreement` 并披露两极 gold。**
  没有第三条路。

---

## 9. 次序与工作量（含成本明示）

| 阶段 | 内容 | 估量 | token |
|---|---|---|---|
| **P−1（前置，非可选路线）** | **v1.5 重定目标**：~~generate 15 行盲标 `gold_answer`+`expected_difficulty`~~ ⇒ 改为三件事 ① **答案键可靠性抽查规程**（冻结前置，见下）；② **已可测项**的出处与口径核对（`expected_kp` 15/15 已有，`gen_coverage` 真判据实测 15/15 pass，不动）；③ **R 可选行**的人工双标指南（若采纳）。`gen_correctness`/`gen_answerability`/`gen_difficulty` 保持 `missing_premise`，**不做事前填充** | 抽查规程约 0.5 人时定案 + 核验按所选样本量；R 若采纳 ≈2–3 人时 | **0** |
| **P−1 冻结前置：答案键可靠性抽查** | 普查事实：674 题里 **160 题（23.7%）源侧无答案键**、**674/674 标为 `scan`（OCR）**、且缺键**按批次分布**（2009 年 11/39 有键 vs 2011/2012/2020/2022/2023/2025 满 40/40）⇒ ①「有没有键」=完整性，②「键对不对」=可靠性，**两件事必须分开**。`gold_source_ref` 只证明**指向哪里**，不证明**那里的键正确**。规程须在**查看抽查结果之前**冻结：总体=有键的 514 题（缺键 160 题单独登记，**不混入正确率分母**）；预先固定随机种子/抽样单位；**按来源文件（年份批次）分层**，不许只抽方便批次；核验**对照原始扫描页**人工重读题干+选项+键（**不得**用同一份 OCR 派生文本自我验证）；预先规定错键的纠正、原始记录保留、扩大抽查或暂停该来源的触发条件；保存抽样清单/核验结果/裁决者/修正历史。★ 样本量由「想以多大把握发现多大比例错键」决定（零接受属性抽样 n=ln(1-c)/ln(1-p)：c=0.95 下 p≥10%→29、p≥5%→59、p≥2%→149），**不得**先挑一个百分比再找理由 | 定案 0.5 人时；执行按 n（59 题 ≈1.5–2 人时） | **0** |

★ **规程已参数化并冻结（checkpoint P−1 裁定一/二）** —— 参数不在文档里靠人抄，而在代码与工件里：

| 冻结项 | 值 | 可复核处 |
|---|---|---|
| 总体 | 有键题 **514** 道（`answer_key` 为单个 A–H，程序现算） | `scripts/p1_key_audit_sample.py` 的 `keyed_atoms()` |
| 样本量 / 目标 | **n=59**；零接受属性抽样：真实错键率 ≥5% 时以 ≥95% 概率至少发现一个 ⇒ `n=ceil(ln(1-c)/ln(1-p))`，**代码自校验**（改 p/c 而 n 不动即 exit 1，牙齿已实测） | 同上 `_design_n()` |
| 抽样单位 | `(question_id, answer_key)` 原子；**清单内不预填源键值**（防核验者被同一份 OCR 派生文本定锚） | `evals/claims/p1_key_audit_sample.json` |
| 分层与硬配额 | 按来源文件=年份；2009/2010/2013/2016 **每层 ≥5**，其余 39 道按有键规模分配（最大余数补齐），合计恰 59 | 同上 `design.strata` 与 `allocation` |
| 种子 | **20261009**（冻结；改种子=换一次抽样，须书面裁定） | 同上 `design.seed` |
| 缺键题 | **160** 道不入任何正确率分母，单独登记为 `missing_key`；★ 不得用模型生成答案、按考点猜答、或把「参考解析为空」解释成「答案已验证」来填 | 普查工件 `evals/claims/p1_corpus_census.json` |
| 核验依据 | **对照原始扫描页人工重读**题干+选项+键；禁止用 `items.md` 自身（同一次 OCR 的产物）自证 | 规程本行 |
| 不足配额 | 记录为「层内不足」，缺口**不得静默挪用**（实测 2016 有键恰 5 道 ⇒ 该层=全查，无缺口） | `design.shortfall_notes` |
| 冻结清单可重算 | `uv run python scripts/p1_key_audit_sample.py --check` ⇒ 清单与脚本重算不一致即红 | 刚实跑 PASS |

★ **发现错键后的处置（★ 待项目所有者确认后才冻结；未冻结前不得据初步结果临场决定扩查）**，提案：
(a) 立即停止引用任何「键可靠」结论；(b) **出错层（年份批次）整体降级**为「来源可靠性未证」，其题目暂不作
gold 出处，直至该层被全查或通过扩查；(c) 扩查 = 出错层内追加至该层有键题的 50%（不足则全查）
**且**对同扫描来源的相邻批次追加 ≥10 题；(d) 错键纠正走 `claims.artifact_status()` 的
`superseded` + `superseded_by`，**保留原键值不覆盖**；(e) 扩查后再现错键 ⇒ 整条 `knowledge/exams`
来源链暂停作为 gold 出处，该维度回落到 limitation 口径。
★ 错键定义预登记：同一题号、同一选项集下源键与扫描页所示键不一致（含字形误读如 B↔8）；
题干/选项不可辨认记 `illegible`，**不算错键**但计入「不可用」并单独披露。
| P0.1 | Evidence Record schema（含 `rerank_status` / `memory_read_status` / `retrieval_status` 三个枚举）+ provenance 五项扩展 | 0.5 天 | 0 |
| P0.2 | tier 表 / registry / 单项四态 / `required_when` / **R5 复合与分母语义** | 0.5 天 | 0 |
| P0.3 | `predicates/` 拆包 + generate/verify/memory 判据（改名 + `missing_premise`）+ **删掉 `metrics.py`/`report.py` 的本地公式副本** | 1 天 | 0 |
| P0.4 | `falsify.py` + 取证矩阵 + `build_claim_ledger` | 1 天 | 0 |
| P1 | **V0**（schema 完整性 + 未测量 predicate 拦截 + AST 禁 default + `gold_source_ref` 必填）+ 文档 4 处勘误 + 数值工件跟踪 | 0.5 天 | 0 |
| P2 | 归因改写落地（judge 的 tier-0 归因门、`memory_read_status`）+ step4fix gate 增故障注入项 | 0.5–1 天 | 0 |
| P3 | **5.A 全部**（B1/B2/B4/B7）+ V5 | **1.5–2 天**（B1 改变被选中文档 ⇒ 下游 evidence/generation/verify/memory 逐条复看；6 条路由需 TEI 就绪 + 索引屏障，机器时间占大头） | 0（门禁本身） |
| P3' | 5.B 择要 + limitation 登记 + 5.C 改口文案 | 0.5 天 | 0 |
| P4 | §7.3 Freeze 全量重跑 | 已有计划 | ledger 取证时间届时整体刷新 |

**合计：约 6.5–7.5 个工程日 + 4 人时人工标注，全程零 token。**
P−1 不排在 P0.3 之前的唯一后果，是 P0.3 交付时 Generate/Grade 两个判据只能写成 `missing_premise`。

**风险**：
1. §4.2 —— R5 一落地，Generate 主指标在补 gold 前**不可出数**；Grade 的 `score_tolerance@±10`
   在两极 gold 下**只证明了对齐二值标注**（`metrics.py:450` 已自陈）。都是真相，不是退步，P−1 可解。
2. B1 重录基线可能让检索指标小幅后退 → 按既有纪律登记 §20.7 并说明理由，禁止静默 `--update-baseline`。
3. 本方案会让若干行的**强度**从「已证明」降为「已测量未证明」，论文里能拍胸脯的行数净减少；
   P−1 是把它们赚回来的唯一路径。
4. 5.B 里的 `difficulty=mixed` 与 `score` 越界会抬升 §6 的 `tool error`；若越过 5% 该行即不达
   ⇒ 这两条自动升级为 5.A（阻塞重跑），届时工作量另加约 0.5 天。
