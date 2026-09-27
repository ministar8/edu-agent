#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step7
PY=.venv/Scripts/python.exe
PROBE=evals/results/step4_c1c2_2026-09-27/scripts/probe_on_temp_index.py

echo "########## diagnose_9（#9 的分数 vs 阈值）##########"
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=off PYTHONPATH=src "$PY" "$OUT/diagnose_9.py" \
  > "$OUT/diagnose_9_after.log" 2>&1
echo "exit=$?"
grep -vE "^(WARNING|DEBUG|INFO|Building|Loading|Prefix|Async Chroma|Failed to parse)" \
  "$OUT/diagnose_9_after.log" | head -26
echo ""

echo "########## probe 表（4 条）##########"
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 PYTHONPATH=src "$PY" "$PROBE" \
  > "$OUT/probe_after.log" 2>&1
echo "exit=$?"
grep -vE "^(WARNING|DEBUG|INFO|Building|Loading|Prefix|Async Chroma|Failed to parse)" \
  "$OUT/probe_after.log" | head -30
echo ""

echo "########## 6 条门禁 ##########"
G=/c/Users/26452/AppData/Local/Temp/edu_step7/gate
mkdir -p "$G"
run() {
  local name="$1"; shift
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate > "$G/$name.log" 2>&1
  echo "--- $name exit=$?"
  grep -E "^(category_hit_at_1|category_hit_at_k|category_mrr|category_precision|empty_result_rate|mean_evidence_count|kp_hit_at_k|kp_mrr) " "$G/$name.log"
  grep -E "门禁通过|退化|\[失败\]" "$G/$name.log" | head -6
  echo ""
}
run q1_fake_off
run q2_fake_on        GATE_RERANK_MODE=on
run q3_fake_disabled  GATE_RERANK_MODE=disabled
run q4_real_off       GATE_USE_REAL_EMBEDDING=1
run q5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run q6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== ALL DONE ====="
