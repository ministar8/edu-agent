#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step8
mkdir -p "$OUT"
PY=.venv/Scripts/python.exe
PROBE=evals/results/step4_c1c2_2026-09-27/scripts/probe_on_temp_index.py

echo "########## probe 表（5 条，含新增 #19）##########"
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 PYTHONPATH=src "$PY" \
  "$PROBE" > "$OUT/probe.log" 2>&1
echo "exit=$?"
grep -vE "^(WARNING|DEBUG|INFO|Building|Loading|Prefix|Async Chroma|Failed to parse)" \
  "$OUT/probe.log" | head -34
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
run k1_fake_off
run k2_fake_on        GATE_RERANK_MODE=on
run k3_fake_disabled  GATE_RERANK_MODE=disabled
run k4_real_off       GATE_USE_REAL_EMBEDDING=1
run k5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run k6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== ALL DONE ====="
