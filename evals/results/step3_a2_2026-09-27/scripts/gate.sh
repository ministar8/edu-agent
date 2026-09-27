#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step3/gate
mkdir -p "$OUT"
PY=.venv/Scripts/python.exe

run() {
  local name="$1"; shift
  echo "########## $name ##########"
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate > "$OUT/$name.log" 2>&1
  echo "exit=$?"
  grep -E "^(category_|empty_|mean_|kp_)" "$OUT/$name.log"
  grep -E "门禁通过|退化|\[失败\]|\[拒绝\]" "$OUT/$name.log" | head -5
  echo ""
}

echo "===== STEP3 GATE START $(date) ====="
run g1_fake_off
run g2_fake_on        GATE_RERANK_MODE=on
run g3_fake_disabled  GATE_RERANK_MODE=disabled
run g4_real_off       GATE_USE_REAL_EMBEDDING=1
run g5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run g6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== STEP3 GATE DONE $(date) ====="
