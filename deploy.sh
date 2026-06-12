#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  deploy.sh — 一键部署脚本
#
#  用法:
#    bash deploy.sh           # 首次部署
#    bash deploy.sh --rebuild # 重新构建镜像
#    bash deploy.sh --stop    # 停止所有服务
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

COMPOSE_CMD="docker compose"

# ── 检查 .env ──
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，从模板复制..."
    cp .env.example .env
    echo "✏️  请编辑 .env 填入 LLM_API_KEY、JWT_SECRET 等必填项后重新运行"
    exit 1
fi

# ── 检查必填变量 ──
for var in LLM_API_KEY JWT_SECRET; do
    if grep -q "^${var}=$" .env || grep -q "^${var}=\s*$" .env; then
        echo "❌ .env 中 ${var} 未填写，请先设置"
        exit 1
    fi
done

# ── 停止 ──
if [ "${1:-}" = "--stop" ]; then
    echo "🛑 停止所有服务..."
    $COMPOSE_CMD down
    echo "✅ 已停止"
    exit 0
fi

# ── 构建 ──
BUILD_FLAG=""
if [ "${1:-}" = "--rebuild" ]; then
    BUILD_FLAG="--build"
fi

echo "🔧 启动服务..."
$COMPOSE_CMD up -d $BUILD_FLAG

# ── 等待后端健康 ──
echo "⏳ 等待后端就绪..."
for i in $(seq 1 30); do
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        echo "✅ 后端已就绪"
        break
    fi
    sleep 2
done

# ── 等待 TEI Embedding 服务就绪 ──
echo "⏳ 等待 TEI Embedding 服务就绪..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11435/health > /dev/null 2>&1; then
        echo "✅ TEI Embedding 已就绪"
        break
    fi
    sleep 2
done

# ── 构建知识库 ──
echo "📚 构建知识库索引 (首次部署必须)..."
docker exec edu-agent-backend-1 python -m app.rag.ingest --rebuild --no-graph 2>/dev/null || \
docker exec backend python -m app.rag.ingest --rebuild --no-graph 2>/dev/null || \
echo "⚠️  知识库构建失败，请手动执行: docker exec <backend容器> python -m app.rag.ingest --rebuild"

# ── 构建知识图谱 (可选，需 Neo4j) ──
echo "🌐 构建知识图谱 (可选，耗时较长)..."
read -p "是否构建知识图谱? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker exec edu-agent-backend-1 python -m app.rag.ingest --rebuild 2>/dev/null || \
    docker exec backend python -m app.rag.ingest --rebuild 2>/dev/null || \
    echo "⚠️  知识图谱构建失败"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  🎉 部署完成！"
echo ""
echo "  访问地址: http://localhost"
echo "  Neo4j Browser: http://localhost:7474"
echo "  后端 API: http://localhost/api/"
echo ""
echo "  常用命令:"
echo "    docker compose logs -f          # 查看日志"
echo "    docker compose restart backend   # 重启后端"
echo "    docker compose down              # 停止"
echo "═══════════════════════════════════════════════════════"
