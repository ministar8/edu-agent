#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step7/narrow
mkdir -p "$OUT"
PY=.venv/Scripts/python.exe
PROBE=evals/results/step4_c1c2_2026-09-27/scripts/probe_on_temp_index.py

echo "########## diagnose_9（收窄变体）##########"
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=off PYTHONPATH=src "$PY" \
  /c/Users/26452/AppData/Local/Temp/edu_step7/diagnose_9.py > "$OUT/diagnose_9.log" 2>&1
echo "exit=$?"
grep -vE "^(WARNING|DEBUG|INFO|Building|Loading|Prefix|Async Chroma|Failed to parse)" \
  "$OUT/diagnose_9.log" | head -20
echo ""

echo "########## probe 表 ##########"
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 PYTHONPATH=src "$PY" \
  "$PROBE" > "$OUT/probe.log" 2>&1
echo "exit=$?"
grep -vE "^(WARNING|DEBUG|INFO|Building|Loading|Prefix|Async Chroma|Failed to parse)" \
  "$OUT/probe.log" | head -26
echo ""

echo "########## 6 条门禁 ##########"
run() {
  local name="$1"; shift
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate > "$OUT/$name.log" 2>&1
  echo "--- $name exit=$?"
  grep -E "^(category_hit_at_1|category_hit_at_k|category_mrr|category_precision|empty_result_rate|mean_evidence_count|kp_hit_at_k|kp_mrr) " "$OUT/$name.log"
  grep -E "门禁通过|退化|\[失败\]" "$OUT/$name.log" | head -6
  echo ""
}
run n1_fake_off
run n2_fake_on        GATE_RERANK_MODE=on
run n3_fake_disabled  GATE_RERANK_MODE=disabled
run n4_real_off       GATE_USE_REAL_EMBEDDING=1
run n5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run n6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== ALL DONE ====="
