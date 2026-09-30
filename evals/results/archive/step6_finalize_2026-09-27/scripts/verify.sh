#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step6/verify
mkdir -p "$OUT"
PY=.venv/Scripts/python.exe

run() {
  local name="$1"; shift
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate > "$OUT/$name.log" 2>&1
  echo "########## $name  exit=$?"
  grep -E "^(category_hit_at_1|category_precision|empty_result_rate|kp_hit_at_k|kp_mrr) " "$OUT/$name.log"
  grep -E "门禁通过|退化|\[失败\]" "$OUT/$name.log" | head -4
  echo ""
}

echo "===== VERIFY START $(date) ====="
run v1_fake_off
run v2_fake_on        GATE_RERANK_MODE=on
run v3_fake_disabled  GATE_RERANK_MODE=disabled
run v4_real_off       GATE_USE_REAL_EMBEDDING=1
run v5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run v6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== VERIFY DONE $(date) ====="
