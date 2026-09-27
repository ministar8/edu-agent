#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step1
PY=.venv/Scripts/python.exe

run() {
  local name="$1"; shift
  echo "########## $name ##########"
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate --update-baseline > "$OUT/$name.log" 2>&1
  local code=$?
  echo "exit=$code"
  grep -E "^(category_|empty_|mean_|kp_)|索引就绪|基线已更新|\[拒绝\]|退化" "$OUT/$name.log"
  echo ""
}

echo "===== REBASELINE START $(date) ====="
run b1_fake_off
run b2_fake_on          GATE_RERANK_MODE=on
run b3_fake_disabled    GATE_RERANK_MODE=disabled
run b4_real_off         GATE_USE_REAL_EMBEDDING=1
run b5_real_on          GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run b6_real_disabled    GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== REBASELINE DONE $(date) ====="
