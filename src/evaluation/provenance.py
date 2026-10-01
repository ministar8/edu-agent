"""实验归档 provenance：让每个 results JSON 自描述「哪版代码 / 哪版黄金集 / 哪个脚本」产生。

为什么需要
----------
冻结前检查（`scripts/freeze_precheck.py`）发现：归档 JSON **不记录代码版本与黄金集哈希**，
从「论文数字」反查到「哪次运行」时，最后一跳只能靠人工维护 `EXPERIMENTS.md §18.0` 的表格。
本模块把这一跳变成自动的：所有写归档的实验脚本统一带上 `provenance` 字段。

用法
----
    from evaluation.provenance import build_provenance

    payload = {"recorded_at": ..., "rows": rows, **build_provenance("scripts/xxx.py")}

字段
----
- `recorded_at`    : UTC ISO 时间戳
- `code_version`   : `<short-sha>`，工作区有未提交改动时加 `-dirty` 后缀
- `golden_sha256`  : 黄金集文件内容哈希（改一个字都会变，用于锁定标注版本）
- `script`         : 生成该归档的脚本相对路径
- `argv`           : 该次运行的命令行参数（不含程序名）
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# src/evaluation/provenance.py → parents[2] = 仓库根
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN = ROOT / "evals" / "datasets" / "golden" / "sample_408.jsonl"


def _git(*args: str) -> str:
    """跑 git 并返回 stdout；任何失败返回空串（provenance 绝不能因 git 缺失而中断实验）。"""
    try:
        out = subprocess.run(
            ["git", *args],
            capture_output=True,
            timeout=15,
            check=False,
            cwd=ROOT,
            encoding="utf-8",
            errors="replace",
        )
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# 判定「代码是否被改动」的范围。
# ★ 只看代码/配置，**不看结果归档** —— 否则「刚跑完实验、归档尚未提交」会被误判成
#   `-dirty`，把「代码有未提交改动」这个真正危险的信号淹没在噪声里。
CODE_PATHS: tuple[str, ...] = ("src", "scripts", "pyproject.toml", ".env.example")


def code_version() -> str:
    """``<short-sha>``，**代码目录**有未提交改动时加 ``-dirty``；git 不可用返回 ``unknown``。"""
    sha = _git("rev-parse", "--short", "HEAD")
    if not sha:
        return "unknown"
    if _git("status", "--porcelain", "--", *CODE_PATHS):
        return f"{sha}-dirty"
    return sha


def golden_sha256(path: str | Path | None = None) -> str:
    """黄金集内容哈希；文件不存在返回 ``missing``。"""
    p = Path(path) if path else DEFAULT_GOLDEN
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def build_provenance(script: str | None = None) -> dict:
    """构造 provenance 片段，供归档 JSON 顶层展开（``**build_provenance(...)``）。

    同时给出顶层 ``recorded_at``（便于快速扫描/排序）与嵌套 ``provenance``（完整溯源）。
    """
    ts = datetime.now(UTC).isoformat()
    return {
        "recorded_at": ts,
        "provenance": {
            "recorded_at": ts,
            "code_version": code_version(),
            "golden_sha256": golden_sha256(),
            "script": script or Path(sys.argv[0]).name,
            "argv": sys.argv[1:],
        },
    }
