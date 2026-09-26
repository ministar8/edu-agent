# 工程化对比：edu-agent vs agent-service-toolkit

> 参考基准：`ministar8/agent-service-toolkit`（`JoshuaC215/agent-service-toolkit` 的 fork）
> 对比时点：2026-09-23（工程化归档 + pre-commit 取回 之后）
> ★ 全文遵循两条判据：**「文件存在 ≠ 实际执行」**、**「只报能归因的数字」**

---

## 0. 一句话结论

上游是**「给所有人用的模板」**——广度优先，覆盖多部署目标（Azure / 多镜像 / 周巡检）、
多维护者自动化（`.claude/` Routine + playbook），但**质量门禁偏松**（codecov patch 不阻塞、无规模/复杂度门槛）。

本项目是**「一个具体毕设」**——深度优先，**自研了三层质量门禁**（检索质量门禁 + 结构规模棘轮 + 分模块覆盖率），
但**交付面窄**（单一镜像、单条 CI、无维护者脚手架）。

**两者不是好坏之分，是「模板」与「交付物」的定位差异。** 本项目在「够用」标准下已达标且有富余。

---

## 1. 逐类对照表（七类 × 双方）

| # | 类别 | 上游模板 | 本项目（当前） | 判定 |
|---|---|---|---|---|
| ① | **依赖与构建** | `pyproject.toml` + `uv.lock`；`[tool.uv] exclude-newer="14 days"`；**uv 版本三处钉死**；依赖组 `dev` / `client` | `pyproject.toml` + `uv.lock`；uv 版本**未钉死**；依赖组 `dev` / **`eval`** | ⚖ 互有：上游有供应链冷却期，我方有独立评测依赖组 |
| ② | **静态检查** | ruff `["I","U"]`；pyrefly `preset=default` + 1 条关闭 | ruff `["I","U","S110","C90"]` + **mccabe 棘轮 25**；pyrefly + **2 个 sub-config** | ✅ **我方更严**（多 S110 / C90，且 25 是实测出来的棘轮） |
| ③ | **pre-commit** | 4 组钩子（+pymarkdown fix/scan） | 4 组钩子（**+evals 基线豁免**，三条适配带理由注释） | ⚖ 相当；上游多 markdown 扫描，我方多基线保护 |
| ④ | **CI 流水线** | 1 条 `test.yml`（3 job：test-python 矩阵 **3.12/3.13/3.14**、lint-markdown、test-docker）+ 3 条 owner-guard workflow | **已归档**（原 5 job，多 `pre-commit` 与自研 `retrieval-quality-gate`） | ⚠ 归档后**我方 CI = 0**；上游矩阵更宽 |
| ⑤ | **容器化** | `docker/Dockerfile.app` + `Dockerfile.service` + `compose.mongo.yaml` | `docker/Dockerfile.service` + `compose.yaml`（**单镜像**） | ⚠ 上游多一个 Streamlit app 镜像 |
| ⑥ | **测试分层** | `tests/`（unit / integration / e2e_ui / smoke） | **已归档**（移出本仓库） | ⚠ 本地无测试套件 |
| ⑦ | **维护者自动化** | `.claude/`（hooks + skills + settings）+ `docs/maintenance/`（3 份 playbook）+ `CLAUDE.md` | `CLAUDE.md`（有）+ `.claude/`（**空目录**） | ❌ 上游明显领先 |

---

## 2. 上游有、我方没有

| 项 | 上游做法 | 是否该补 |
|---|---|---|
| **`[tool.uv] exclude-newer = "14 days"`** | 供应链冷却：只装发布 ≥14 天的包，防「刚投毒的新版本」 | ❌ 不必。毕设不面向生产；且会拖慢首次构建可复现性 |
| **uv 版本三处钉死** | CI `0.12.5` / Dockerfile `pip install uv==0.12.5` / `.claude/hooks/ensure-pinned-uv.sh` 从 Dockerfile **反解** | △ **可选**。真正的价值是「三处一致」——单钉一处等于没钉 |
| **`Dockerfile.app`** | 独立的 Streamlit 前端镜像 | ❌ 我方是静态前端（`static/`），由 service 直接托管，不需要第二镜像 |
| **`compose.mongo.yaml`** | 可选的 MongoDB 记忆后端 | ❌ 我方用 SQLite（`store.db` / `checkpoints.db`），毕设够用 |
| **Azure 部署 `deploy.yml`** | 推 main 即部署 | ❌ 毕设无 Azure 账号；且**该 workflow 带 owner-guard，在 fork 里本来就不执行** |
| **线上周巡检 `live-smoke-test.yml`** | 周日 cron 跑 Playwright 打线上应用 | ❌ 无线上环境。**同样带 owner-guard，fork 中死代码** |
| **`template-cleanup.yml`** | 首次实例化时自删维护者脚手架 | ❌ 纯模板机制，与毕设无关 |
| **`scripts/smoke_test.sh`** | ★ **反静默回退**：除 API 检查外，还回查容器/DB/langfuse 确认**真的用了那个依赖** | △ **值得学思路**。我们本地 TEI 排查时已吃过「`/health` 200 ≠ 就绪」的亏 |
| **`.claude/` 维护者 Routine** | SessionStart hooks + skills + 5 条 GitHub MCP 危险操作 deny | ❌ 属「单人长期维护大仓」的投入，毕设阶段不划算 |
| **`docs/maintenance/` playbook** | 3 份 Routine（Daily Sentinel / Weekly / CI Follow-Through）+「no self-wake-ups」原则 | ❌ 同上 |
| **`client` 依赖组** | 只装 httpx/pydantic/streamlit 即可跑前端 | ❌ 我方 `src/client/` 已归档（零运行时引用），没有对应的精简依赖组 |

---

## 3. 我方有、上游没有（自研增量）

> ★ 标「已归档」的项随测试套件移出本仓库 —— 或代码/配置已移走，或留在 `pyproject.toml`
> 里但**没有执行者**。

| 项 | 说明 | 价值 |
|---|---|---|
| **★ 检索质量门禁** | `evaluation.retrieval_gate`：按 `(embedding, rerank)` 组合分路由（默认 / `GATE_RERANK_MODE=on` / `=disabled` / `GATE_USE_REAL_EMBEDDING=1`）各比一份基线，容差 0.02，**跨口径比对与未登记组合直接拒（退出码 2）**，并有「路由前提自检」抓静默回退 | 上游**完全没有**「RAG 质量」这一维度的门禁。这是本项目最核心的技术资产 |
| **★ 圈复杂度棘轮** | `mccabe max-complexity = 25`，恰等于「当前最复杂函数」→ 开启时 0 命中，**只拦新增** | 上游无任何规模/复杂度门槛 |
| **★ 分模块覆盖率门槛**（已归档） | 强制显式 `--cov=src/`，`tools/` 与离线入库链不计入 | 上游只有全局 codecov 上报 |
| **codecov patch 阻塞**（已归档） | 我方要求 **target 80% 且阻塞**，且有量化立论 | 上游 `codecov.yml` 是 **`informational: true`（不阻塞）** |
| **pyrefly 2 个 sub-config** | `src/rag/**` 关 7 项、`src/tools/**` 关 8 项，**逐项带迁移理由** | 上游只有 1 条 `bad-specialization = false` |
| **`eval` 依赖组** | `ragas` / `datasets` 独立分组，**默认不装**（故代码里 6 处 `# type: ignore[import-not-found]`） | 上游无评测依赖组 |
| **`evals/` 基线集** | 3 份基线 JSON + 1 份 `sample_408.jsonl`，且 pre-commit 专门豁免空白改写 | 上游无 |
| **`src/tools/`** | 数据清洗 / 分块 / 入库工具链（5 文件） | 上游无离线知识加工链 |

---

## 4. 归档后的现状（本项目）

**已移出到 `../edu-agent-engineering-archive/`：**

| 原路径 | 归档位置 | 现状 |
|---|---|---|
| `.github/` | `batch2/github/` | 已移出 → **本工作区无 CI** |
| `tests/` | `batch2/tests/` | 已移出 → **本地跑不了测试** |
| `codecov.yml` | `batch2/codecov.yml` | 已移出 |
| `coverage.json` | `batch2/coverage.json` | 已移出 |
| `scripts/*.py`（3 个） | `batch2/scripts_*.py` | 已移出 |
| `docs/ENGINEERING.md` | `batch1/docs_ENGINEERING.md` | 已移出 |
| `src/client/` | `batch1/src_client` | 已移出（零运行时引用；与其测试 `tests/client/` 团聚） |
| `tests/client/` | `batch1/tests_client` | 仍在归档（无测试套件） |
| `.pre-commit-config.yaml` | `batch2/pre-commit-config.yaml` | ★ **已取回并三处适配** |

**当前仍保留的工程化：**
`.pre-commit-config.yaml` · `docker/Dockerfile.service` · `compose.yaml` · `.dockerignore` ·
`pyproject.toml`（含 ruff / pyrefly / pymarkdown 配置）· `uv.lock` · `evals/` ·
`docs/`（4 篇）· `scripts/tei_deploy.ps1`

**空目录待决：** `.claude/`（存在但无文件）→ 建议移出或删除，避免「看起来有、其实没有」的误导。

---

## 5. 按「够用 = 毕设 + Docker + 清晰结构」的取舍建议

| 建议 | 理由 |
|---|---|
| **不加任何 CI workflow** | 完全符合用户既定的「够用」标准。★ 但要意识到：**门禁代码还在 `pyproject.toml` 里，却无人自动执行** —— 提交前靠 pre-commit 兜 |
| **不加 `.claude/` / `docs/maintenance/`** | 那是给长期维护开源大仓的投入，与毕设不对齐 |
| **不加多镜像 / Azure / 周巡检** | 无对应部署目标；且上游那几条在 fork 中本就是死代码 |
| **可考虑补：uv 版本钉死** | 若要让「别人 clone 下来能复现构建」，这是最低成本的一步。但要**三处一起钉** |
| **建议清理：`.claude/` 空目录** | 空目录会误导读者以为项目有维护者脚手架 |
| **★ 反思：门禁 vs 无 CI 的张力** | 当前是「有严格门禁配置，但没有强制执行者」。**答辩时应主动说明**：门禁通过 pre-commit 在本地强制，CI 部分为归档状态 |

---

## 6. 双方定位差异（根本原因）

```
上游模板：广度优先              本项目：深度优先
├── 服务「任意下游用户」          ├── 服务「一个具体毕设」
├── 多部署目标（Azure/多镜像）    ├── 单部署目标（本地 Docker）
├── 多维护者自动化（.claude）     ├── 无长期维护者
├── 质量门禁偏松（不阻塞）        └── 质量门禁偏严（三层自研）
└── 因此需要「模板清洁」机制
```

**上游的复杂度是「被使用者数量」逼出来的；本项目的复杂度是「问题难度」逼出来的。**
本项目把投入放在**检索质量**（这是 408 答疑的真正难点），上游把投入放在**交付广度**（这是模板的真正价值）。
