#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step4/gate
mkdir -p "$OUT"
PY=.venv/Scripts/python.exe

run() {
  local name="$1"; shift
  echo "########## $name ##########"
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate > "$OUT/$name.log" 2>&1
  echo "exit=$?"
  grep -E "^(category_|empty_|mean_|kp_)" "$OUT/$name.log"
  grep -E "门禁通过|退化|\[失败\]|\[拒绝\]" "$OUT/$name.log" | head -6
  echo ""
}

echo "===== STEP4 GATE START $(date) ====="
run s1_fake_off
run s2_fake_on        GATE_RERANK_MODE=on
run s3_fake_disabled  GATE_RERANK_MODE=disabled
run s4_real_off       GATE_USE_REAL_EMBEDDING=1
run s5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run s6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== STEP4 GATE DONE $(date) ====="
