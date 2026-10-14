# golden/ —— 检索门禁的输入（尺子的基准）

## 文件

| 文件 | 条数 | 用途 |
|---|---|---|
| `sample_408.jsonl` | 156 | **检索质量门禁主输入**：`retrieval_gate` 的 156 条黄金 query |
| `retrieval_probes.jsonl` | 5 | `probe_gate` 的小节级探针（目标 chunk 在哪一层丢失） |

## sample_408.jsonl 的结构

一行一条：`{"query", "reference", "metadata"}`。

- `metadata.subject`：`ds | co | os | network`（四科各 39 条）。★ 门禁侧映射见
  `evaluation.gates.retrieval_gate._constants.SUBJECT_TO_CATEGORY`；
  注意**知识库 KP 索引用 `cn` 指代计算机网络**，与这里的 `network` 是同一学科两套编码。
- `metadata.query_type`：`concept | generate | grade | code`（156/156 全覆盖；`generate` 会被门禁
  特殊判为「讲义或真题二者之一」的合法来源，见 `load_golden_queries` docstring）。
- `metadata.knowledge_points`：章级 KP 标注，156/156 全覆盖。命中判定走
  `chapter_of_source`（文件名 stem + `_CHAPTER_ALIASES` → 中文章名），**不是** KP 树节点名。
- `reference`：参考答案要点，供 context_recall / faithfulness 类指标用，不出现在检索门禁判定里。

## 2026-10-14 修订（★ 动过门禁输入，登记见 EXPERIMENTS.md §20.7.4）

| 修订 | 处数 | 原因 |
|---|---|---|
| KP 标注假阴性修复 | 4 | `输入输出管理`×2→`输入输出系统`（章在、文件名标签不一致）、`磁盘调度`→`文件管理`（原标注指错章）、`操作系统概述`→`计算机系统概述`（命名断茬）。修复前这 4 条的 `kp_hit@k` 恒为 0 |
| 补 `query_type: concept` | 40 | 前 40 条概念题与后 20 条同标，消除同题不同标 |

影响：默认路由 `kp_hit_at_k` 0.9231→0.9487、`kp_mrr` 0.8041→0.8174，其余指标不变；
**sha256 由 `be98912a` 变为 `783e78ff`**，六条路由基线已同批重录。

## 修改纪律

改本目录任一文件 = 动门禁输入 ⇒ ① 跑 `python -m evaluation.gates.retrieval_gate` 看 diff；
② 指标变化必须 `--update-baseline` 重录并在 EXPERIMENTS.md 登记（禁止静默重录）；
③ KP 标注改前先过 hittability 审计：标注值必须能在该科知识库文件名派生的章标签里查到
（2026-10-14 的 4 处就是这么发现的）。
