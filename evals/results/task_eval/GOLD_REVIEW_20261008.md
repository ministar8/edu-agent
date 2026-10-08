# Gold 人工审核工作单 · 2026-10-08

> **这张表是给你读和勾的，不是生效的那一份。** 生效的永远是 `evals/datasets/demo/*_cases.jsonl` 里的 gold 行；
> 表里的勾选不会自动进数据集 —— 流程是「**看表 → 改数据集对应那一行 → 跑 sanity → 翻 `gold_status`**」。

## 一、现状（全部来自代码与文件，零成本核对）

- `gold_sanity`：**ERROR 0**，PENDING 1 条（grade 的两极 gold，已用 `verdict_agreement` 处置，**不是待补标**）。
- 66 条全是 `gold_status=draft` ⇒ §7.2 论文表与 §7.3 Freeze 都卡在这里。
- 要逐条看的只有 **30 条**：grade 15（校验 `answer_key`）+ generate 15（`gold_answer`）。qa / verify / memory 的 gold 已由 sanity 机械校验过，抽查即可。

## 二、Grade 15 条 —— 校验扫描来的 `answer_key`

★ 为什么必须人看：源数据实测 **24% 缺失、抽样 15 条里 5 条错**；而 `build_demo_cases.py:233` 的 `human_score = 100 if student == correct else 0`
  是**按 key 机械推**的 ⇒ key 错则 human_score 错 ⇒ `verdict_agreement` 测的就是 gold 质量而不是系统能力。

| case | 题干（节选） | 学生作答 | 满分 | 扫描 key | 预填 human | 出处 | 判定 |
|---|---|---|---|---|---|---|---|
| grd-001 | 在 OSI参考模型中，自下而上第一个提供端到端服务的层次是 。 A. 数据链路层 B. 传输层  | B | 100.0 | B | 100.0 | 2009-Q33 | ☐对 ☐错 |
| grd-002 | 冯·诺依曼计算机中指令和数据均以二进制形式存放在存储器中， CPU 区分它们的依据 是 。 A. | B | 100.0 | C | 0.0 | 2009-Q11 | ☐对 ☐错 |
| grd-003 | 为解决计算机主机与打印机之间速度不匹配问题，通常设置一个打印数据缓冲区，主机将要输出 的数据依次 | B | 100.0 | B | 100.0 | 2009-Q1 | ☐对 ☐错 |
| grd-004 | 一个 C 语言程序在一台 32 位机器上运行。程序中定义了三个变量x、y 和 z，其中 x 和  | C | 100.0 | D | 0.0 | 2009-Q12 | ☐对 ☐错 |
| grd-005 | FTP 客户和服务器间传递 FTP 命令时，使用的连接是 。 A. 建立在 TCP 之上的控制连 | A | 100.0 | A | 100.0 | 2009-Q40 | ☐对 ☐错 |
| grd-006 | 下列关于 RISC 的叙述中，错误的是 。 A. RISC 普遍采用微程序控制器 B. RISC | D | 100.0 | A | 0.0 | 2009-Q17 | ☐对 ☐错 |
| grd-007 | 设栈 S 和队列 Q的初始状态均为空，元素 a, b, c, d, e, f, g 依次进入栈  | C | 100.0 | C | 100.0 | 2009-Q2 | ☐对 ☐错 |
| grd-008 | 某计算机系统中有 8 台打印机，由K 个进程竞争使用，每个进程最多需要 3 台打印机。该系统可  | A | 100.0 | C | 0.0 | 2009-Q25 | ☐对 ☐错 |
| grd-009 | 如果本地域名服务器无缓存，当采用递归方法解析另一网络某主机域名时，用户主机、本地域 名服务器发送 | B | 100.0 | B | 100.0 | 2010-Q40 | ☐对 ☐错 |
| grd-010 | 下列选项中，能缩短程序执行时间的措施是 。 I. 提高 CPU 时钟频率 II. 优化数据通路结 | B | 100.0 | D | 0.0 | 2010-Q12 | ☐对 ☐错 |
| grd-011 | 己知一棵完全二叉树的第 6 层（设根为第 1 层）有 8 个叶结点，则该完全二又树的结点个数最多 | C | 100.0 | C | 100.0 | 2009-Q5 | ☐对 ☐错 |
| grd-012 | 下列选项中，满足短任务优先且不会发生饥饿现象的调度算法是 。 A. 先来先服务 B. 高响应比优 | C | 100.0 | B | 0.0 | 2011-Q23 | ☐对 ☐错 |
| grd-013 | TCP/IP 参考模型的网络层提供的是 。 A. 无连接不可靠的数据报服务 B. 无连接可靠的数 | A | 100.0 | A | 100.0 | 2011-Q33 | ☐对 ☐错 |
| grd-014 | 下列选项中的英文缩写均为总线标准的是 。 A. PCI、CRT、USB、EISA B. ISA  | A | 100.0 | D | 0.0 | 2010-Q20 | ☐对 ☐错 |
| grd-015 | 下列关于无向连通图特性的叙述中，正确的是 。 I. 所有顶点的度之和为偶数 II. 边数大于顶点 | A | 100.0 | A | 100.0 | 2009-Q7 | ☐对 ☐错 |

（`notes` 里没带 answer_key 的行数 = 0，这些尤其要看。）
**发现错的时候改哪里（两个通道，别混）**：

- **grade 的 gold 错**（human_score / key）⇒ 改 `evals/datasets/demo/grade_cases.jsonl` 那一行的 `gold.human_score` 与 `notes` 里的 `answer_key=`。
- **真题语料本身的 key 错**（Verify 用的 L3 items）⇒ 加进 `evals/datasets/exam_answer_corrections.json`：
  它是**评测侧覆盖表**，不改 KB 原文，由 `evaluation/task_eval/assets.py:94` 读取。

## 三、Generate 15 条 —— `gold_answer`

| case | query（节选） | expected_kp | 现在的 gold_answer | 现在的 difficulty | 你要做的 |
|---|---|---|---|---|---|
| gen-001 | 请出一道考查 Cache 映射与地址划分的题。 | co.storage | （空） | （空） | ☐补答案 ☐不动 |
| gen-002 | 请出一道考查二叉树遍历与重建的题。 | ds.tree | （空） | （空） | ☐补答案 ☐不动 |
| gen-003 | 请出一道考查 TCP 序号与确认号的题。 | cn.transport | （空） | （空） | ☐补答案 ☐不动 |
| gen-004 | 请出一道考查进程同步的题。 | os.process | （空） | （空） | ☐补答案 ☐不动 |
| gen-005 | 请出一道考查相对寻址的题。 | co.instruction | （空） | （空） | ☐补答案 ☐不动 |
| gen-006 | 请出一道考查最小生成树的题。 | ds.graph | （空） | （空） | ☐补答案 ☐不动 |
| gen-007 | 请出一道考查子网划分与路由聚合的题。 | cn.network | （空） | （空） | ☐补答案 ☐不动 |
| gen-008 | 请出一道考查页面置换算法的题。 | os.memory | （空） | （空） | ☐补答案 ☐不动 |
| gen-009 | 请出一道考查指令流水线的题。 | co.cpu | （空） | （空） | ☐补答案 ☐不动 |
| gen-010 | 请出一道考查哈希冲突处理的题。 | ds.search | （空） | （空） | ☐补答案 ☐不动 |
| gen-011 | 请出一道考查 CRC 校验的题。 | cn.datalink | （空） | （空） | ☐补答案 ☐不动 |
| gen-012 | 请出一道考查文件物理结构的题。 | os.file | （空） | （空） | ☐补答案 ☐不动 |
| gen-013 | 请出一道考查 IEEE 754 浮点数表示的题。 | co.representation | （空） | （空） | ☐补答案 ☐不动 |
| gen-014 | 请出一道考查堆排序的题。 | ds.sort | （空） | （空） | ☐补答案 ☐不动 |
| gen-015 | 请出一道考查奈氏准则与香农公式的题。 | cn.physical | （空） | （空） | ☐补答案 ☐不动 |

★ 这两个字段的**后果不一样**，填之前要知道：

- `gold_answer` **有读者**：`judge.build_judge_prompt()` 会把非空 gold 字段拼进【gold】块 ⇒ 填了它，**judge 的输入就变了**，
  `final_quality` 与 Generate 主指标必须在同一份新输入下重跑才有意义。★ 顺带说：这正是压住 **#36**
  （judge 不重算算术、`gen-001` 算错却拿 5.0）最省事的办法 —— 给 judge 一份参考答案，它就有东西可比。
- `expected_difficulty` 的读者只有 judge 块和 `metrics.difficulty_match(expected, None)`；后者第二参数恒 `None`
  ⇒ **按构造就是 N/A**（§20.5.1 的「双重断开死项」）。所以**不要为没指定难度的 query 编一个难度**：
  既填不上死项，又给 judge 塞一个凭空假设的 gold。按 §21 维持「难度匹配 n/a(15)」的披露。

## 四、审完之后的顺序（别错）

```bash
# 1) 改完数据集先机械校验
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -c "from evaluation.task_eval.cases import load_demo; from evaluation.task_eval.gold_sanity import run_sanity; r=run_sanity(load_demo()); print('ERROR', len(r.errors), 'PENDING', len([i for i in r.issues if i.level=='PENDING']))"
# 2) 试跑翻转器（不写盘），看清要改哪几条、指纹会变成什么
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/gold_review_apply.py --ids qa-001,grd-002 --status reviewed
# 3) 确认后落地，并按它印出的新值同步 docs/EXPERIMENTS.md §20.0 的效果集指纹
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/gold_review_apply.py --ids-file confirmed.txt --status reviewed --apply
# 4) 然后才是 §7.3 Freeze 全量重跑 —— gold 一改，之前的数字就属「draft gold 下的读数」
```

★ `--all-draft` 存在，但它等于「一次签 66 份」—— 只有你真的逐条看过之后才许用。
