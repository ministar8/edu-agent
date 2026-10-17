# 前端体检报告 · 2026-10-17（预优化，论文截图前）

> **背景**：项目已冻结（tag `V-2026-10-16` 评测冻结 / `P-2026-10-16` 项目级冻结，`origin/main` = `dd1c861`）。
> owner 指示：论文要放系统截图 ⇒ **先把前端改到终态再截图**；方向未定 ⇒ 先全面体检。
> 本报告即体检结果：**静态通读 7 个前端文件 + 动态实测（Playwright/Chromium 实跑服务，19 张截图）+ HTTP 契约核验**。
> 冻结范围不含 `static/` 与 `src/service/`（FREEZE_DECLARATION §1/§4），本报告及后续优化不触碰 evals/、gold、claims/。

## 1. 总体评价

前端底子**明显高于预期**：设计令牌化（颜色/圆角/阴影单一来源）、暗色主题只覆盖令牌、WCAG AA 对比度有据可查、三档响应式断点、`prefers-reduced-motion` 已照顾、markdown 渲染「先转义后渲染」天然防 XSS、SSE 双流（token/message）+ 检索阶段进度 + 引用溯源折叠块齐备。代码注释密度与防御性编程（randomUUID/clipboard/隐私模式兜底）符合本项目一贯水准。

**但距「论文截图终态」有 3 个高优先问题**：练习页二次生成会清空已答题目（实测复现）、批改请求漏传后端契约字段、**DashScope LLM 账号欠费**（环境问题，直接决定截图能拍什么）。另有约 15 个中低优先项。

## 2. 问题清单（按优先级）

### 高 —— 论文截图/演示前必须解决

| # | 问题 | 证据 | 影响 | 修复 | 位置 |
|---|---|---|---|---|---|
| H1 | **练习页「生成题目」清空旧题**：再出第二题时，第一题的作答、批改结果、参考答案全部丢失 | 实测：生成「进程死锁」并填入作答 → 生成「图的最短路径」⇒ `question-cards=1`（旧卡连同作答被 `innerHTML=""` 清掉）；截图 `practice_wipe_bug.png` | 论文演示连续出题即暴露；练习功能实际不可用（出一题丢一题） | `renderQuestions` 改增量 append；每题卡加独立「重新生成本题」；提供显式「清空」 | `static/app.js:666` `renderQuestions` |
| H2 | **批改请求漏传 `batch_id`/`question_id`**：后端 `GradeRequest` 两字段存在且 memory episode 的 KP 关联依赖它们（缺它 ⇒ `compute_weak_topics` 退回「题干前 80 字」legacy fallback）；前端把 generate 返回的 `data.batch_id` 直接丢弃 | `src/service/service.py:497-502` 注释明示；`static/app.js:746-750` 只发 stem/standard_answer/user_answer | 「薄弱点分析」数据完整性受损；前后端契约缺口 | 前端缓存 batch_id（generate 响应里已有），批改时随传 | `static/app.js:744` |
| H3 | **DashScope LLM 账号欠费（环境，需 owner 处理）** | 实测服务日志：`LLM call failed [classify/decompose/grading]: 400 Access denied ... 'type': 'Arrearage'` | qwen 负责的查询分类/子问题拆解/批改**全部失败**；出题走题库兜底（返回 200 但非 LLM 生成）、批改 500、聊天降级（deepseek 仍可完整作答+引用，见 `chat_with_citations.png`） | 充值或切换 judge/aux 模型配置；**否则论文截图只能拍聊天（降级态），拍不了批改** | `.env` / `src/core/settings.py` |

### 中 —— 影响截图观感或功能完整性

| # | 问题 | 证据 | 修复 |
|---|---|---|---|
| M1 | **favicon 404**：无 icon 链接，浏览器自动请求 `/favicon.ico` → 404 | 实测 `curl /favicon.ico -> 404` | 加 `static/favicon.svg` + `<link rel="icon">`（纯前端） |
| M2 | **流式回答无「停止生成」**：`sending` 锁死到流结束，fetch 无 `AbortController`；LLM 卡住时用户只能干等 | `static/app.js:482-486` | AbortController + 停止按钮 |
| M3 | **滚动锁定**：每个 SSE chunk 都 `scrollToBottom()`，用户上翻阅读时被强行拽回底部 | `static/app.js:594` | 仅在「用户已在底部」时跟随 |
| M4 | **新会话首次加载 `/api/history` 必 500**（后端）：`state_snapshot.values["messages"]` 在 values 为 `{}` 时 KeyError，被吞成通用 500；前端静默显示空态 | 实测复现：新 thread_id ⇒ `{"code":"internal_error"}` 500；浏览器控制台同步 | 后端 1 行：`.values.get("messages") or []`（需动 `src/service/`，改后复跑 pytest/ruff） |
| M5 | **批改反馈纯文本**：`feedback.textContent`，不走 markdown 渲染，与聊天气泡的渲染能力不一致（评语常含列表/加粗） | `static/app.js:759` | 统一走 `renderMarkdown` |
| M6 | **出题数量固定 1 题**：`count: 1` 硬编码，UI 无数量选择，练习流单薄 | `static/app.js:644` | 加 1/3/5 数量选择 |
| M7 | **可访问性缺标签**：`#chat-input` 与动态创建的作答 textarea 无 `aria-label`；消息区无 `aria-live` | `static/index.html:48`、`static/app.js:724` | 补 aria 属性 |

### 低 —— 打磨项

| # | 问题 | 位置 |
|---|---|---|
| L1 | 出题错误文案用 `innerHTML` 拼接后端 message（模式不安全，其余处均用 textContent） | `static/app.js:646` |
| L2 | 批改错误态简陋：「批改失败」裸文本，无图标/重试（实测截图 14） | `static/app.js:752` |
| L3 | `height: 100vh` 在移动端动态地址栏下会溢出，建议 `100dvh` 渐进增强 | `static/style.css:340` |
| L4 | 占位符对比度 `--hint #a1a1aa` on `#fff` ≈ 2.9:1（正文已达 AA，placeholder 属豁免但偏灰） | `static/style.css:25` |
| L5 | 历史记录里的 tool 消息平铺，长会话刷屏，可折叠 | `static/style.css:601` |
| L6 | ≤680px 侧栏顶栏内容超出 359px 需内部横滚（实测元素 right 至 617px；设计内行为，可隐藏次要项优化） | `static/style.css:967-982` |
| L7 | 登录页 `apiGet(API.me)` 无 `.catch`，后端离线时控制台未处理 rejection | `static/auth.js:4` |
| L8 | thinking 指示器 100ms 刷新可降频至 250ms（性能微调，可选） | `static/app.js:521` |

## 3. 实测通过的基线（优化时不许破坏）

- **登录流**：表单原生校验、加载态（转圈）、错误展示、`HttpOnly; SameSite=lax` cookie 下发、401 跳转；
- **明暗主题**：head 同步加载无 FOUC、localStorage 持久、跟随系统偏好、切换按钮 aria-label；
- **markdown 渲染**：转义优先防 XSS、表格/代码块/列表/引用/标题齐全；
- **SSE 契约**：`retrieval_stage` 阶段事件 → 前端 STAGE_LABELS 映射正确（实测 classify→plan→decompose→recall 顺序下发）；token/message 双流；`[DONE]` 收尾；
- **引用溯源**：`retrieval_docs` 按 chunk_id 去重、`<details>` 折叠、分数/重排分/摘录展示（截图 `chat_with_citations.png`）；
- **聊天降级路径**：qwen 分类失败后 deepseek 作答 + 引用完整渲染（截图 15）；
- **响应式**：375px 实测 `docScrollWidth = 375 = innerWidth`（无页面级横向溢出；网上流传的「黑带」为截图查看器伪影，像素测量最右列全白）；
- **无 JS 异常**：`pageerror` 0 条；控制台仅 401/500 资源错误（均对应已知后端问题 M4/H3）。

## 4. 修复顺序建议（截图前）

- **P0（阻塞截图）**：H3 充值/切模型（owner 人工）→ H1 清空缺陷 → H2 batch_id 透传 → M1 favicon → M5 反馈 markdown → M6 题数选择；
- **P1（截图观感）**：M2 停止按钮 → M4 history 500（后端 1 行）→ M7 aria → L2 错误态；
- **P2（打磨）**：其余低项，按余力。

其中 **H1/H2/M1/M2/M3/M5/M6/M7/L1–L8 全部可在 `static/` 内闭合**（零 Python 改动，门禁天然不受影响）；**M4 需动 `src/service/`**（改后必须复跑 ruff/pytest）。

## 5. 复现方式

```bash
uv run python src/run_service.py                          # 起服务 :8000
uv run python docs/frontend_audit/audit_browser_round1.py # 第一轮：登录/主题/出题/截图
uv run python docs/frontend_audit/audit_browser_round2.py # 第二轮：清空缺陷/错误态/移动端
```
（两脚本用 Playwright 驱动 Chromium，输出落 `%TEMP%/edu_audit_shots/`；轮次 1 的 grade 步骤因 LLM 欠费会超时，属预期。）

## 6. 体检产物与副作用登记

- 截图证据（4 张，已入 `docs/frontend_audit/`）：`login_light.png` / `chat_with_citations.png` / `practice_wipe_bug.png` / `main_mobile.png`；完整 19 张在 TEMP；
- 测试账号 `audit_20261017`（id=11，本地 `edu_agent.db`，密码 `auditpass123`）——**刻意保留**，便于 owner 自查 UI；
- 服务重启重建了 `checkpoints.db`/`store.db`（gitignored 运行态；冻结纪律约束的是 git 状态与证据链，运行态文件随服务生命周期生灭，不受影响）；
- 实测期间 LLM 欠费（H3）导致批改/分类失败——**未修改任何代码/配置**。
