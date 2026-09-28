# TEI 部署：本地 embedding（bge-m3）+ reranker（bge-reranker-v2-m3）
# 唯一部署入口；日常启停用 docker start/stop，不要反复 docker run 重建。
#
#   .\scripts\tei_deploy.ps1
#   .\scripts\tei_deploy.ps1 -Stop
#
# 端口默认与 .env 对齐：embedding 11435、rerank 11436。
# 校验用 scripts/tei_ready.py（走项目调用路径），不要手写 curl。

param(
    [string]$EmbeddingModelPath = 'D:\models\Embedding\bge-m3',
    [string]$RerankerModelPath = 'D:\models\Reranker\bge-reranker-v2-m3',
    [string]$EmbeddingModelId = 'BAAI/bge-m3',
    [string]$RerankerModelId = 'BAAI/bge-reranker-v2-m3',
    [string]$Image = 'ghcr.io/huggingface/text-embeddings-inference:89-1.7',
    [int]$EmbeddingPort = 11435,
    [int]$RerankerPort = 11436,
    [switch]$Stop,
    [switch]$SkipVerify
)

$ErrorActionPreference = 'Stop'
$ContainerEmbed = 'tei-embedding'
$ContainerRerank = 'tei-rerank'  # 现网容器名，不要写成 tei-reranker

function Assert-Docker {
    docker version --format '{{.Server.Version}}' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker daemon is not available. Start Docker Desktop / Engine first.'
    }
}

function Start-TeiContainer {
    param(
        [string]$Name,
        [string]$ModelArg,
        [string]$MountSource,
        [string]$MountTarget,
        [int]$Port,
        [string[]]$ExtraArgs
    )

    $filter = 'name=^' + $Name + '$'
    $existing = @(docker ps -a --filter $filter --format '{{.Names}}')
    if ($existing -contains $Name) {
        $running = @(docker ps --filter $filter --format '{{.Names}}')
        if ($running -contains $Name) {
            Write-Host ('[skip] ' + $Name + ' already running')
        } else {
            Write-Host ('[start] ' + $Name)
            docker start $Name | Out-Null
        }
        return
    }

    Write-Host ('[create] ' + $Name + '  model=' + $ModelArg + '  port=' + $Port + ':80')
    $cmd = @(
        'run', '-d',
        '--name', $Name,
        '--gpus', 'all',
        '-p', ($Port.ToString() + ':80'),
        '--restart', 'unless-stopped'
    )
    if ($MountSource) {
        if (-not (Test-Path $MountSource)) {
            throw ('Local model path not found: ' + $MountSource + '. Fix the path or use -EmbeddingModelId/-RerankerModelId for HuggingFace IDs.')
        }
        $cmd += @('-v', ($MountSource + ':' + $MountTarget))
        if ($Name -eq $ContainerRerank) {
            $cmd += @('-e', 'HF_HUB_OFFLINE=1')
        }
    }
    $cmd += $Image
    $cmd += @('--model-id', $ModelArg)
    if ($ExtraArgs) {
        $cmd += $ExtraArgs
    }
    docker @cmd | Out-Null
}

Assert-Docker

if ($Stop) {
    Write-Host ('[stop] ' + $ContainerEmbed + ' ' + $ContainerRerank)
    docker stop $ContainerEmbed $ContainerRerank 2>$null | Out-Null
    exit 0
}

# embedding: prefer local weights
$embedModelArg = $EmbeddingModelId
$embedMount = $null
$embedTarget = '/data/bge-m3'
if (Test-Path $EmbeddingModelPath) {
    $embedModelArg = $embedTarget
    $embedMount = $EmbeddingModelPath
}
Start-TeiContainer -Name $ContainerEmbed -ModelArg $embedModelArg `
    -MountSource $embedMount -MountTarget $embedTarget `
    -Port $EmbeddingPort -ExtraArgs @()

# reranker: prefer local weights; same flags as production containers
$rerankModelArg = $RerankerModelId
$rerankMount = $null
$rerankTarget = '/data/bge-reranker-v2-m3'
if (Test-Path $RerankerModelPath) {
    $rerankModelArg = $rerankTarget
    $rerankMount = $RerankerModelPath
}
Start-TeiContainer -Name $ContainerRerank -ModelArg $rerankModelArg `
    -MountSource $rerankMount -MountTarget $rerankTarget `
    -Port $RerankerPort `
    -ExtraArgs @('--dtype', 'float16', '--max-batch-tokens', '2048')

if ($SkipVerify) {
    Write-Host 'Skip verify. Wait 30-60s for model load, then run scripts/tei_ready.py.'
    exit 0
}

Write-Host ''
Write-Host 'Model load takes ~30-60s. Running readiness check via scripts/tei_ready.py ...'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root 'src'
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    $py = 'python'
}
& $py (Join-Path $root 'scripts\tei_ready.py')
exit $LASTEXITCODE
