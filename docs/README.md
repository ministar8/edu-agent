# docs/ 索引

**先读哪个**：

- 动知识库 → `KB_MASTER_DESIGN.md`（总册）
- 写论文 / 快速定位代码 → `ARCHITECTURE_RETRIEVAL.md` + `ARCHITECTURE.md`
- 部署 → `DOCKER.md`
- 答辩提问 / 职责边界 → `RAG_BOUNDARY_MAP.md`

---

## 现行文档

| 文件 | 作用 | 何时读 |
|------|------|--------|
| `ARCHITECTURE.md` | 系统总体设计（分层、调用链、8 阶段检索链、评测体系） | 理解系统结构、写论文第 3 章 |
| `ARCHITECTURE_RETRIEVAL.md` | 检索架构总览（as-built）+ 术语表 + 模块索引 + 已知局限 | 读检索代码前 |
| `KB_MASTER_DESIGN.md` | 知识库总册（L1/KP/L2/L3 + 边 + gap + ID + 现状） | 动知识库/入库前 |
| `RAG_BOUNDARY_MAP.md` | RAG 边界地图（停靠点 / 数据真源 / 技术债台账 + 答辩三十秒版本） | 答辩提问 / 判断职责归属 |
| `DOCKER.md` | 容器部署、健康检查、TEI 端点契约 | 起容器 / 探活 TEI 前 |

---

## 本地运行检查（替代原 CI）

| 检查项 | 命令 | 说明 |
|--------|------|------|
| 依赖安装 | `uv sync` | 创建 `.venv` 并安装依赖 |
| 代码风格 | `uv run ruff check src/` | Lint（含 S110、C90） |
| 代码格式 | `uv run ruff format --check src/` | 格式检查（不改文件） |
| 类型检查 | `uv run pyrefly check` | 类型检查（须 0 错误） |
| 单元测试 | `uv run pytest -q` | 纯本地 I/O，无网络无密钥 |
| 启动服务 | `uv run python src/run_service.py` | http://127.0.0.1:8000 |
| 知识库构建 | `uv run python -m rag.ingest` | learning_paths 增量入库 |
| E2E 演示 | `.venv/Scripts/python.exe scripts/ops/e2e_chat_demo.py --skip-tei` | 注册→登录→问答→历史 |

> Windows 下运行带 emoji 的脚本请设置 `PYTHONIOENCODING=utf-8`，否则打印 `✅` 会因 GBK 崩溃。
