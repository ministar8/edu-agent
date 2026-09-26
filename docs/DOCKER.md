# Docker 部署与运行

面向「把服务跑起来 + 让别人也能跑起来」这一最小目标。深度架构说明见 `ARCHITECTURE.md`。

## 组成

| 文件 | 作用 |
|---|---|
| `docker/Dockerfile.service` | 后端镜像（FastAPI + Agent + RAG） |
| `compose.yaml` | 服务编排：端口、env、volume、健康检查、开发热同步 |
| `.dockerignore` | 构建上下文裁剪（排除 `.venv` / `chroma_db` / `*.db` / `tests` 等） |

## 快速开始

前置：本机已装 Docker Desktop / Docker Engine，且**守护进程已在运行**。

```bash
docker compose up --build        # 构建并前台启动
docker compose up --build -d     # 后台启动
docker compose logs -f           # 跟踪日志
docker compose down              # 停止并移除容器
```

启动后访问 `http://127.0.0.1:8000/`（静态前端由 FastAPI 一并提供）。

## 镜像构建要点

Dockerfile 的关键选择及理由：

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/   # uv 版本钉死，可复现
ENV UV_PROJECT_ENVIRONMENT=/usr/local \                   # 装进系统 Python，不另建 venv
    UV_COMPILE_BYTECODE=1                                 # 预编译 .pyc，冷启动更快
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev        # 只用锁文件，且不装 dev 组
COPY src/ ./src/                                          # 只拷运行所需
COPY static/ ./static/
COPY knowledge/ ./knowledge/
CMD ["python", "src/run_service.py"]
```

三点值得注意：

1. **`--frozen`**：严格按 `uv.lock` 安装，构建结果可复现；lock 与 pyproject 不一致时直接失败。
2. **`--no-dev`**：`dev` 依赖组（pytest / ruff / pyrefly / pre-commit）不进镜像，减小体积。
3. **依赖先于源码 COPY**：改代码不会让依赖层缓存失效，重建更快。

## 数据与卷挂载

`compose.yaml` 挂载两项，**不打进镜像**：

| 挂载 | 说明 |
|---|---|
| `./knowledge:/app/knowledge` | 408 知识库语料（改了不用重建镜像） |
| `./chroma_db:/app/chroma_db` | ChromaDB 向量库（运行时产物，且体积大） |

`.dockerignore` 里排除 `chroma_db` / `*.db` **与** compose 挂载它们并不矛盾：
前者是「不烤进镜像层」，后者是「运行时挂载」。数据不该固化进镜像。

SQLite 库（`edu_agent.db` / `checkpoints.db` / `store.db`）默认在容器内生成。
**若希望持久化，需自行加 volume 挂载**，否则 `docker compose down` 后会话与用户数据会丢失。

## 环境变量

`compose.yaml` 用 `env_file: .env` 注入配置。首次运行前：

```bash
cp .env.example .env     # 必填：DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY、JWT_SECRET
```

★ 容器内访问宿主机上的 TEI（embedding / reranker）时，**`localhost` 不可用**——
容器内的 localhost 指向容器自身。需改为：

- Docker Desktop（Windows/macOS）：`host.docker.internal`
- Linux：宿主机网桥 IP，或让容器使用 `network_mode: host`

即 `.env` 里的 `EMBEDDING_API_BASE` / `RERANK_LOCAL_URL` 要相应调整。这是容器化最常见的踩坑点。

## 健康检查

compose 已配置，探针打 `/health`：

```yaml
healthcheck:
  test: ["CMD", "python", "-c",
         "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

用 `docker compose ps` 查看健康状态。

> 注意：`/health` 会检查外部依赖（TEI / LLM）。**依赖未就绪时健康检查会持续失败**，
> 但服务本身可能已能响应请求。排查时不要只看健康状态。

## 开发热同步

```bash
docker compose watch        # 源码改动 → 同步进容器 → 自动重启
```

`compose.yaml` 的 `develop.watch` 逐包列出 `src/` 下的目录。
★ **新增包必须同步补进该列表**，否则改动不会同步、热重载形同虚设
（`2026-09-23` 就补过遗漏的 `src/prompts/`——它是运行期依赖，漏了会导致提示词改动不生效）。

## 常见问题

| 现象 | 排查方向 |
|---|---|
| `failed to connect to the docker API ... dockerDesktopLinuxEngine` | Docker 守护进程未运行。`docker --version` 只报客户端版本，不代表守护进程在跑；用 `docker ps` 或 `tasklist \| grep -i docker` 确认 |
| 构建时找不到依赖 | `uv.lock` 与 `pyproject.toml` 不一致。本地先跑 `uv lock` 再构建 |
| 容器起但检索报错 | TEI 地址问题，见上文「环境变量」小节 |
| 改了代码没生效 | 未用 `compose watch`，或该包不在 `develop.watch` 列表内 |
| 数据丢失 | SQLite 库未挂载 volume，`down` 后随之删除 |

## 与其他运行方式的关系

| 方式 | 命令 | 适用 |
|---|---|---|
| 本地裸跑 | `uv run python src/run_service.py` | 开发调试最快（见 README 快速开始） |
| Docker Compose | `docker compose up --build` | 演示 / 交付 / 换环境复现 |
| LangGraph Studio | `langgraph dev` | 调试 agent 图结构 |

三者共用同一份 `src/` 与配置口径，差异只在运行环境。
