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
    print("① 代码状态（V-2026-11-05 是否可定位到不可变引用）")
    print(f"  HEAD            : {git('rev-parse', '--short', 'HEAD')}")
    print(f"  HEAD 提交信息    : {git('log', '-1', '--format=%s')}")
    dirty = git("status", "--porcelain")
    files = [ln for ln in dirty.splitlines() if ln.strip()]
    # 只看代码目录（与 evaluation.provenance.code_version 同一判据）：
    # 「刚跑完实验、归档未提交」不算代码改动，否则真正的危险信号会被淹没。
    code_dirty = [ln for ln in files if ln.split(maxsplit=1)[-1].startswith(("src/", "scripts/"))]
    print(f"  工作区改动文件数 : {len(files)}（其中代码目录 {len(code_dirty)}）")
    if code_dirty:
        print("  → 判定：❌ 代码有未提交改动，无法用 SHA 唯一定位")
    else:
        print("  → 判定：✅ 代码目录干净，可用 HEAD SHA 定位（归档改动不影响）")
    for ln in code_dirty[:10]:
        print(f"     {ln}")
    if len(code_dirty) > 10:
        print(f"     … 另有 {len(code_dirty) - 10} 项")


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
        "retrieval/ablation/component_ablation_20261104_full156_deepseek41.json",
        "retrieval/ablation/rerank_compare_20261105_deepseek41.json",
        "retrieval/layer_policy/layer_ablation_20261105_full156_deepseek41_withfull.json",
        "retrieval/ablation/basic_rag_compare_20261105_deepseek41.json",
        "retrieval/layer_policy/task_mode_x_layer_policy_20261105_deepseek41.json",
        "retrieval/legacy_runtime/legacy_runtime_20261105_deepseek41.json",
        "retrieval/ablation/component_variance/summary.json",
        "retrieval/ablation/threshold_sensitivity/threshold_sensitivity_full_20261105_deepseek41.json",
        "retrieval/ablation/threshold_sensitivity/threshold_sensitivity_vector_only_20261105_deepseek41.json",
        "retrieval/ablation/l2_coverage_20261105_deepseek41.json",
        "generation/ragas/ragas_freeze20261105.json",
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
        # ★ 2026-11-05 修：原判据只认 `scripts/` 目录，漏掉 `src/` 下的产出脚本
        #   （实测 RAGAS 归档 `provenance.script = src/evaluation/ragas/ragas_eval.py`
        #   被判成「无脚本」）。改为认 provenance 的 `script` 键或任意 `.py` 路径。
        script = ('"script"' in blob) or ("scripts/" in blob) or (".py" in blob)
        print(
            f"  {rel:<56}{'Y' if ts else '-':<4}{'Y' if cfg else '-':<5}"
            f"{'Y' if golden else '-':<8}{'Y' if code else '-':<6}{'Y' if script else '-'}"
        )
    print(
        "\n  列说明：ts=有时间戳  cfg=有参数快照  golden=记录了黄金集  code=记录了代码版本  脚本=记录了生成脚本"
    )

    # ★ 2026-11-05 补：上面那一列只证明「归档里**写了**脚本路径」，不证明「那个脚本还在库」。
    #   实测两张表（5.3 L2 覆盖 / 5.4 legacy 池策略）的产出脚本是当时的临时脚本、已不在仓库 ⇒
    #   归档自描述齐全，但数字**无法按记载复现**。冻结前必须把这类缺口显式列出来。
    print("  脚本存在性（provenance.script 是否在库）：")
    missing: list[str] = []
    moved: list[str] = []
    for rel in targets:
        d = load(R / rel) or {}
        inner = (d.get("provenance") or {}).get("provenance") or d.get("provenance") or {}
        sp = str(inner.get("script") or "")
        if not sp:
            continue
        repo = Path(__file__).resolve().parents[2]
        if (repo / sp).exists():
            continue
        candidates = list(repo.glob(f"scripts/**/{Path(sp).name}")) + list(
            repo.glob(f"src/**/{Path(sp).name}")
        )
        if candidates:
            moved.append(f"{sp} → {candidates[0].relative_to(repo).as_posix()}（{rel}）")
        else:
            missing.append(f"{sp}（{rel}）")
    if not missing and not moved:
        print("    全部在库")
    for m in missing:
        print(f"    ✗ 缺失 {m}")
    for m in moved:
        print(f"    ~ 路径已迁移 {m}")


def check_doc_to_json() -> None:
    print("\n" + "=" * 96)
    print("④ 文档数字 → JSON 抽样反查（论文表 2 的 full 行）")
    d = load(R / "retrieval/ablation/component_ablation_20261104_full156_deepseek41.json") or {}
    row = next((r for r in d.get("rows", []) if r["config"] == "full"), None)
    print("  paper_tables 表 2 full kp_mrr 应为 0.8309")
    print(f"  component_ablation_20261104_full156_deepseek41.json full → {row}")
    print(f"  该 JSON 的 config_snapshot.full = {(d.get('config_snapshot') or {}).get('full')}")
    print(f"  该 JSON 的 golden / limit      = {d.get('golden')} / {d.get('limit')}")


if __name__ == "__main__":
    check_code_state()
    check_golden()
    check_archives_traceability()
    check_doc_to_json()
