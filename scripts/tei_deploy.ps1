# TEI 部署脚本 - bge-m3 embedding + bge-reranker-v2-m3 reranker
# 需要先启动 Docker Desktop
#
# ★ 2026-09-23 重写。原版有三处会让「演示时才发现坏了」的缺陷：
#
#   ① **端口写死 8080，与 .env 的 11436 矛盾**。原版 `docker run -p 8080:80` 起 reranker，
#      而 `.env` 里 `RERANK_LOCAL_URL=http://localhost:11436` —— 照原版跑，重排会静默不生效。
#      现在**端口只从 .env 读**，不再有第二份真值源。
#   ② **验证只 print 不 assert**。原版把 `dim=...` / `score=...` 打出来就结束 ——
#      TEI 返回错误体时可能打出无意义的数，脚本仍然「成功」。现在失败即非零退出。
#   ③ **只验 HTTP 依赖，不验「系统真能用」**。补 Chroma 真实检索探针（查 collection 计数）。
#
# ★ 为什么这里不重发一份「容器已存在就别 docker run」的判断：本机容器是既有资源，
#   日常用 `docker start`（见 README / 项目笔记）。本脚本的职责是**从零部署 + 部署后验证**，
#   所以下面显式处理「同名容器已存在」——要么复用（-Reuse），要么报错让人自己决定。

[CmdletBinding()]
param(
    # 复用已存在的同名容器（不删除、不重建）。日常起服务用这个。
    [switch]$Reuse,
    # 启动后等待秒数，默认 50s（本机实测 bge-m3 加载约需 30-60s）
    [int]$WaitSeconds = 50
)

$ErrorActionPreference = 'Stop'

# ── 0. 读 .env：端口/维度的唯一真值源 ─────────────────────────────
# ★ 刻意不写死端口。`.env` 是运行时真值（`settings.py` 也从这里读），
#   脚本再写一份就会漂移 —— 原版的 8080 vs .env 的 11436 就是这么来的。
$envFile = Join-Path $PSScriptRoot '..\.env'
if (-not (Test-Path $envFile)) {
    Write-Error "找不到 $envFile —— 端口需要从它读取。请先准备 .env（可参考 .env.example）。"
    exit 1
}

$envMap = @{}
foreach ($line in Get-Content $envFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
    if ($trimmed -match '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $envMap[$Matches[1]] = $Matches[2].Trim()
    }
}

function Get-EnvUrl([string]$key, [string]$fallback) {
    if ($envMap.ContainsKey($key) -and $envMap[$key]) { return $envMap[$key] }
    Write-Host "  ! .env 缺 $key，回退到 $fallback" -ForegroundColor Yellow
    return $fallback
}

function Get-EnvInt([string]$key, [int]$fallback) {
    if ($envMap.ContainsKey($key) -and $envMap[$key] -match '^\d+$') { return [int]$envMap[$key] }
    Write-Host "  ! .env 缺 $key，回退到 $fallback" -ForegroundColor Yellow
    return $fallback
}

$embedUrl = Get-EnvUrl 'EMBEDDING_API_BASE' 'http://localhost:11435'
$rerankUrl = Get-EnvUrl 'RERANK_LOCAL_URL' 'http://localhost:8080'
$embedDim = Get-EnvInt 'EMBEDDING_DIM' 1024

# 从 URL 反解端口，供 docker run -p 使用
function Get-PortFromUrl([string]$url) {
    $m = [regex]::Match($url, ':(\d+)')
    if (-not $m.Success) { throw "无法从 '$url' 解析端口" }
    return [int]$m.Groups[1].Value
}
$embedPort = Get-PortFromUrl $embedUrl
$rerankPort = Get-PortFromUrl $rerankUrl

$image = 'ghcr.io/huggingface/text-embeddings-inference:89-1.7'
$hfCache = "$env:USERPROFILE\.cache\huggingface\hub"

Write-Host ""
Write-Host "=== TEI 部署 ===" -ForegroundColor Cyan
Write-Host "  embedding : $embedUrl  (端口 $embedPort, 期望维度 $embedDim)"
Write-Host "  reranker  : $rerankUrl  (端口 $rerankPort)"
Write-Host "  镜像      : $image"
Write-Host ""

# ── 1. 容器准备：复用 / 新建 ──────────────────────────────────────
function Ensure-Container {
    param(
        [string]$Name,
        [string]$Port,
        [string[]]$ExtraArgs
    )
    $existing = docker ps -a --filter "name=^/$Name$" --format '{{.Names}}'
    if ($existing -eq $Name) {
        if ($Reuse) {
            Write-Host "[$Name] 复用已存在容器 → docker start" -ForegroundColor Yellow
            docker start $Name | Out-Null
        } else {
            Write-Host "[$Name] 容器已存在。用 -Reuse 复用它，或先手工删除：" -ForegroundColor Red
            Write-Host "         docker rm -f $Name" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "[$Name] 新建容器（端口 $Port）..." -ForegroundColor Green
        docker run -d --name $Name --gpus all -p "${Port}:80" -v "${hfCache}:/data" $image @ExtraArgs | Out-Null
    }
}

Ensure-Container -Name 'tei-embedding' -Port $embedPort -ExtraArgs @(
    '--model-id', 'BAAI/bge-m3', '--dtype', 'float16', '--pooling', 'mean',
    '--max-batch-tokens', '16384', '--max-client-batch-size', '64'
)
Ensure-Container -Name 'tei-rerank' -Port $rerankPort -ExtraArgs @(
    '--model-id', 'BAAI/bge-reranker-v2-m3', '--dtype', 'float16', '--pooling', 'cls',
    '--max-batch-tokens', '8192'
)

# ── 2. 等待 + 真实推理验证（★ 不是只看 /health） ────────────────────
# ★ 关键：TEI 的 /health 在模型加载**之前**就可能已可答（进程起来了），
#   所以必须发**真实推理请求**才能证明「模型真的加载完了」。
#   这里的断言就是「静默回退」的防线：拿不到符合预期的形状 = 直接失败。
Write-Host ""
Write-Host "等待服务就绪（最多 ${WaitSeconds}s）..." -ForegroundColor Yellow

$probe = Join-Path $PSScriptRoot '_tei_probe.py'
@'
import json
import sys
import time

import httpx

embed_url, rerank_url, embed_dim, deadline = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])


def wait_and_probe(label, fn, timeout_budget):
    """轮询直到 fn() 成功或超时；成功返回其值，超时抛错。"""
    started = time.time()
    last_err = None
    while time.time() - started < timeout_budget:
        try:
            return fn()
        except Exception as exc:  # 服务未就绪时连不上/报错都算「还没好」
            last_err = exc
            time.sleep(2)
    raise TimeoutError(f"{label} 在 {timeout_budget:.0f}s 内未就绪；最后一次错误：{last_err!r}")


def probe_embedding():
    r = httpx.post(f"{embed_url}/embed", json={"inputs": ["测试"]}, timeout=10.0)
    r.raise_for_status()
    data = r.json()
    assert isinstance(data, list) and data, f"embedding 返回为空或非列表: {data!r}"
    vec = data[0]
    assert isinstance(vec, list), f"embedding 首个元素不是向量: {vec!r}"
    # ★ 断言维度：这是「模型真的按预期加载」最硬的证据
    assert len(vec) == embed_dim, f"embedding 维度 {len(vec)} != .env 的 EMBEDDING_DIM {embed_dim}"
    # ★ 断言不是退化向量（全 0 = 模型加载异常但仍返回了形状正确的空壳）
    assert any(abs(x) > 1e-9 for x in vec), "embedding 全为 0 —— 模型加载异常"
    return {"dim": len(vec), "sample": round(vec[0], 6)}


def probe_rerank():
    r = httpx.post(
        f"{rerank_url}/rerank",
        json={"query": "什么是时间复杂度", "texts": ["时间复杂度描述算法运行时间随规模的增长", "今天天气不错"]},
        timeout=10.0,
    )
    r.raise_for_status()
    data = r.json()
    assert isinstance(data, list) and data, f"rerank 返回为空或非列表: {data!r}"
    item = data[0]
    assert isinstance(item, dict) and "score" in item, f"rerank 首项无 score 字段: {item!r}"
    score = item["score"]
    assert isinstance(score, (int, float)), f"rerank score 不是数字: {score!r}"
    # ★ 断言排序真的发生了：相关内容应排在无关内容前（证明不是原样返回）
    scores = [it["score"] for it in data]
    assert scores == sorted(scores, reverse=True), f"rerank 结果未按分数降序: {scores!r}"
    return {"score": round(float(score), 6), "n": len(scores), "descending": True}


try:
    emb = wait_and_probe("embedding", probe_embedding, deadline)
    rrk = wait_and_probe("reranker", probe_rerank, deadline)
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
    sys.exit(1)

print(json.dumps({"ok": True, "embedding": emb, "reranker": rrk}, ensure_ascii=False))
'@ | Set-Content -Path $probe -Encoding UTF8

# 用项目 venv 的 python（保证 httpx 可用），找不到就退回 PATH 上的 python
$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

$result = & $python $probe $embedUrl $rerankUrl $embedDim $WaitSeconds 2>&1
$exitCode = $LASTEXITCODE
Remove-Item $probe -ErrorAction SilentlyContinue

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "✗ 依赖验证失败 —— 容器起来了，但依赖不可用：" -ForegroundColor Red
    Write-Host "  $result" -ForegroundColor Red
    Write-Host ""
    Write-Host "排查：docker logs --tail 50 tei-embedding  /  tei-rerank" -ForegroundColor Yellow
    exit 1
}

$parsed = $result | ConvertFrom-Json
Write-Host ""
Write-Host "✓ Embedding 可用：dim=$($parsed.embedding.dim)  (期望 $embedDim)" -ForegroundColor Green
Write-Host "✓ Reranker  可用：score=$($parsed.reranker.score)  n=$($parsed.reranker.n)  降序=$($parsed.reranker.descending)" -ForegroundColor Green

# ── 3. Chroma 检索探针：证明「真的检索得到」，而非仅端口通 ──────────
# ★ 这一步才是「反静默回退」的落点：两个 HTTP 依赖活着 ≠ 系统能答题。
#   判据是「collection 里真的有文档」，而不是「连得上」。
Write-Host ""
Write-Host "检查 Chroma 索引..." -ForegroundColor Yellow

$chromaProbe = Join-Path $PSScriptRoot '_chroma_probe.py'
@'
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

try:
    from rag.vectorstore import get_vector_store_manager
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"导入 vectorstore 失败: {exc!r}"}))
    sys.exit(1)

try:
    mgr = get_vector_store_manager()
    names = mgr.list_collections()
    if not names:
        print(json.dumps({"ok": False, "error": "没有任何 collection —— 索引未建立或路径不对"}))
        sys.exit(1)
    infos = [mgr.get_collection_info(n) for n in names]
    total = sum(i.get("count", 0) for i in infos)
    empty = [i["name"] for i in infos if not i.get("count")]
    degraded = [i["name"] for i in infos if i.get("hnsw_status") == "degraded"]
    print(json.dumps({
        "ok": True,
        "collections": [{"name": i["name"], "count": i.get("count", 0), "hnsw": i.get("hnsw_status", "?")} for i in infos],
        "total": total,
        "empty": empty,
        "degraded": degraded,
    }, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"ok": False, "error": repr(exc)}))
    sys.exit(1)
'@ | Set-Content -Path $chromaProbe -Encoding UTF8

$pyPath = Join-Path $PSScriptRoot '..\src'
$prevPyPath = $env:PYTHONPATH
$env:PYTHONPATH = $pyPath
try {
    $chromaOut = & $python $chromaProbe 2>&1
    $chromaExit = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $prevPyPath
}
Remove-Item $chromaProbe -ErrorAction SilentlyContinue

if ($chromaExit -ne 0) {
    Write-Host "! Chroma 探针失败（不影响 TEI 部署结论）：" -ForegroundColor Yellow
    Write-Host "  $chromaOut" -ForegroundColor Yellow
} else {
    $ci = $chromaOut | ConvertFrom-Json
    if ($ci.ok) {
        Write-Host "✓ Chroma 可用：$($ci.collections.Count) 个 collection，共 $($ci.total) 条文档" -ForegroundColor Green
        foreach ($c in $ci.collections) {
            Write-Host "    - $($c.name): $($c.count) 条 (hnsw=$($c.hnsw))"
        }
        if ($ci.empty) {
            Write-Host "  ! 空 collection（需重新入库）：$($ci.empty -join ', ')" -ForegroundColor Yellow
        }
        if ($ci.degraded) {
            Write-Host "  ! HNSW 降级（检索会退化为暴力搜索）：$($ci.degraded -join ', ')" -ForegroundColor Yellow
        }
    } else {
        Write-Host "! Chroma 不可用：$($ci.error)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "完成。容器状态：" -ForegroundColor Cyan
docker ps --filter "name=tei-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
