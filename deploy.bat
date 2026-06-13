@echo off
REM ═══════════════════════════════════════════════════════════════
REM  deploy.bat — Windows 一键部署脚本
REM  面向本机 Docker Compose 部署；不会修改源码或提交文件。
REM ═══════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion

REM ── 检查 .env ──
if not exist .env (
    echo [WARN] 未找到 .env 文件，从模板复制...
    copy .env.example .env
    echo 请编辑 .env 填入 LLM_API_KEY、JWT_SECRET 等必填项后重新运行
    exit /b 1
)

REM ── 解析参数 ──
set "ACTION=up"
if "%~1"=="--stop" set "ACTION=stop"
if "%~1"=="--rebuild" set "ACTION=rebuild"

if "%ACTION%"=="stop" (
    echo 停止所有服务...
    docker compose down
    echo 已停止
    exit /b 0
)

REM ── 构建 ──
set "BUILD_FLAG="
if "%ACTION%"=="rebuild" set "BUILD_FLAG=--build"

echo 启动服务...
docker compose up -d %BUILD_FLAG%

REM ── 等待后端健康 ──
echo 等待后端就绪...
set "READY=0"
for /L %%i in (1,1,30) do (
    if !READY!==0 (
        curl -sf http://localhost/health >nul 2>&1
        if !errorlevel!==0 (
            set "READY=1"
            echo 后端已就绪
        ) else (
            timeout /t 2 /nobreak >nul
        )
    )
)

REM ── 拉取 Ollama 模型 ──
echo 拉取 bge-m3 Embedding 模型...
for /f "tokens=*" %%c in ('docker compose ps -q ollama 2^>nul') do (
    docker exec %%c ollama pull bge-m3 2>nul || echo [WARN] Ollama 模型拉取失败，请手动执行
)

REM ── 构建知识库 ──
echo 构建知识库索引...
for /f "tokens=*" %%c in ('docker compose ps -q backend 2^>nul') do (
    docker exec %%c python -m app.rag.ingest --rebuild --no-graph 2>nul || echo [WARN] 知识库构建失败，请手动执行
)

echo.
echo ====================================================
echo   部署完成！
echo.
echo   访问地址: http://localhost
echo   Neo4j Browser: http://localhost:7474
echo   后端 API: http://localhost/api/
echo.
echo   常用命令:
echo     docker compose logs -f          查看日志
echo     docker compose restart backend   重启后端
echo     docker compose down              停止
echo ====================================================
