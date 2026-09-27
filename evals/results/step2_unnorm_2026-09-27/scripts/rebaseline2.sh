#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step1
PY=.venv/Scripts/python.exe

run_once() {
  local name="$1"; shift
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate --update-baseline --force-baseline > "$OUT/$name.log" 2>&1
  return $?
}

run() {
  local name="$1"; shift
  local attempt=1
  while [ $attempt -le 3 ]; do
    echo "########## $name (attempt $attempt) ##########"
    run_once "$name" "$@"
    local code=$?
    echo "exit=$code"
    grep -E "^(category_|empty_|mean_|kp_)|基线已更新|\[拒绝\]|\[失败\]" "$OUT/$name.log"
    if [ $code -eq 0 ]; then
      echo ""
      return 0
    fi
    if grep -q "检索期查询异常" "$OUT/$name.log"; then
      echo "-> Chroma 落盘竞态，重试"
      attempt=$((attempt+1))
      sleep 3
      continue
    fi
    echo "-> 非竞态失败，停止"
    echo ""
    return 1
  done
  echo "-> 重试耗尽"
  echo ""
  return 1
}

echo "===== REBASELINE-2 START $(date) ====="
run c1_fake_off
run c2_fake_on          GATE_RERANK_MODE=on
run c3_fake_disabled    GATE_RERANK_MODE=disabled
run c4_real_off         GATE_USE_REAL_EMBEDDING=1
run c5_real_on          GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
echo "===== REBASELINE-2 DONE $(date) ====="
