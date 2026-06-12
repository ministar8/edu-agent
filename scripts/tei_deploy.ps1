# TEI 部署脚本 - bge-m3 embedding + bge-reranker-v2-m3 reranker
# 需要先启动 Docker Desktop

# ── 1. Embedding 服务 (bge-m3, port 11435) ──
# 使用本地 HuggingFace 缓存避免重复下载
$hfCache = "$env:USERPROFILE\.cache\huggingface\hub"

docker run -d `
  --name tei-embedding `
  --gpus all `
  -p 11435:80 `
  -v "${hfCache}:/data" `
  ghcr.io/huggingface/text-embeddings-inference:latest `
  --model-id BAAI/bge-m3 `
  --dtype float16 `
  --pooling mean `
  --max-batch-tokens 16384 `
  --max-client-batch-size 64

# ── 2. Reranker 服务 (bge-reranker-v2-m3, port 8080) ──
docker run -d `
  --name tei-reranker `
  --gpus all `
  -p 8080:80 `
  -v tei-reranker-cache:/data `
  ghcr.io/huggingface/text-embeddings-inference:latest `
  --model-id BAAI/bge-reranker-v2-m3 `
  --dtype float16 `
  --pooling cls `
  --max-batch-tokens 8192

# ── 3. 验证 ──
Write-Host "等待服务启动（约30-60秒）..." -ForegroundColor Yellow
Start-Sleep -Seconds 45
python -c "import httpx; r=httpx.post('http://localhost:11435/embed',json={'inputs':['test']}); print(f'Embedding: dim={len(r.json()[0])}')"
python -c "import httpx; r=httpx.post('http://localhost:8080/rerank',json={'query':'test','texts':['hello']}); print(f'Reranker: score={r.json()[0][\"score\"]:.4f}')"
