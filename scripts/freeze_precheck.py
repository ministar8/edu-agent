"""最终冻结前检查：四层可追溯链闭环验证（只读）。

层：代码版本 → golden dataset → 实验脚本/参数 → 归档 JSON → 文档数字
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

R = Path("evals/results")
GOLDEN = Path("evals/datasets/golden/sample_408.jsonl")


def git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            capture_output=True,
            timeout=30,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return (out.stdout or out.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return f"<git 调用失败: {e}>"


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def check_code_state() -> None:
    print("=" * 96)
    print("① 代码状态（V-2026-10-02 是否可定位到不可变引用）")
    print(f"  HEAD            : {git('rev-parse', '--short', 'HEAD')}")
    print(f"  HEAD 提交信息    : {git('log', '-1', '--format=%s')}")
    dirty = git("status", "--porcelain")
    files = [ln for ln in dirty.splitlines() if ln.strip()]
    tracked_mod = [ln for ln in files if not ln.startswith("??")]
    print(f"  未提交改动文件数 : {len(files)}（其中已跟踪 {len(tracked_mod)}）")
    if tracked_mod:
        print("  → 判定：❌ 版本节点无不可变引用（代码改动未提交，无法用 SHA 定位）")
    else:
        print("  → 判定：✅ 工作区干净，可用 HEAD SHA 定位")
    for ln in files[:14]:
        print(f"     {ln}")
    if len(files) > 14:
        print(f"     … 另有 {len(files) - 14} 项")


def check_golden() -> None:
    print("\n" + "=" * 96)
    print("② 黄金集版本")
    data = GOLDEN.read_bytes()
    print(f"  文件      : {GOLDEN}")
    print(f"  sha256    : {hashlib.sha256(data).hexdigest()}")
    rows = [
        ln
        for ln in GOLDEN.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    print(f"  条数      : {len(rows)}")
    print("  → 该哈希是否被任何归档/文档记录：", "见下（脚本未写入则为空）")


def check_archives_traceability() -> None:
    print("\n" + "=" * 96)
    print("③ 归档 JSON 自描述性（能否反查到脚本 / 参数 / 代码版本）")
    targets = [
        "retrieval/ablation/component_ablation.json",
        "retrieval/ablation/rerank_compare.json",
        "retrieval/layer_policy/layer_ablation.json",
        "retrieval/ablation/task_layer_ablation.json",
        "retrieval/ablation/basic_rag_compare.json",
        "retrieval/layer_policy/task_mode_x_layer_policy.json",
        "retrieval/legacy_runtime/legacy_runtime.json",
        "retrieval/ablation/component_variance/summary.json",
        "retrieval/ablation/threshold_sensitivity/threshold_sensitivity.json",
        "retrieval/ablation/l2_coverage.json",
        "generation/ragas/metrics.json",
    ]
    hdr = f"  {'归档':<56}{'ts':<4}{'cfg':<5}{'golden':<8}{'code':<6}{'脚本'}"
    print(hdr)
    print("  " + "-" * 92)
    for rel in targets:
        p = R / rel
        d = load(p) or {}
        blob = json.dumps(d, ensure_ascii=False)
        ts = bool(d.get("recorded_at") or (d.get("_meta") or {}).get("recorded_at"))
        cfg = ("config_snapshot" in d) or ("design" in d)
        golden = ("sample_408" in blob) or ("golden" in blob) or ("golden_hash" in blob)
        code = ("code_version" in blob) or ("commit" in blob) or ("git_sha" in blob)
        script = "scripts/" in blob
        print(
            f"  {rel:<56}{'Y' if ts else '-':<4}{'Y' if cfg else '-':<5}"
            f"{'Y' if golden else '-':<8}{'Y' if code else '-':<6}{'Y' if script else '-'}"
        )
    print(
        "\n  列说明：ts=有时间戳  cfg=有参数快照  golden=记录了黄金集  code=记录了代码版本  脚本=记录了生成脚本"
    )


def check_doc_to_json() -> None:
    print("\n" + "=" * 96)
    print("④ 文档数字 → JSON 抽样反查（论文表 2 的 full 行）")
    d = load(R / "retrieval/ablation/component_ablation.json") or {}
    row = next((r for r in d.get("rows", []) if r["config"] == "full"), None)
    print("  paper_tables 表 2 full kp_mrr 应为 0.9625")
    print(f"  component_ablation.json full → {row}")
    print(f"  该 JSON 的 config_snapshot.full = {(d.get('config_snapshot') or {}).get('full')}")
    print(f"  该 JSON 的 golden / limit      = {d.get('golden')} / {d.get('limit')}")


if __name__ == "__main__":
    check_code_state()
    check_golden()
    check_archives_traceability()
    check_doc_to_json()
