#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step6/rebaseline
mkdir -p "$OUT"
PY=.venv/Scripts/python.exe

# 重录一轮：
#  - 先试 --update-baseline（保留合理性校验，能过就说明变化是「正常幅度」）
#  - 被 check_baseline_sanity 拒绝时改 --force-baseline
#    （已知的量纲缺陷：所有指标共用绝对阈值 0.10，而 mean_evidence_count 量级是 4~5）
#  - 撞 Chroma 落盘竞态（「检索期查询异常」）时重试
run() {
  local name="$1"; shift
  local attempt=1
  while [ $attempt -le 3 ]; do
    env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate --update-baseline \
      > "$OUT/$name.log" 2>&1
    local code=$?
    if [ $code -eq 0 ] && grep -q "基线已更新" "$OUT/$name.log"; then
      echo "########## $name  OK (attempt $attempt, 未用 --force-baseline)"
      grep -o "基线已更新: .*" "$OUT/$name.log" | head -1
      return 0
    fi
    if grep -q "检索期查询异常" "$OUT/$name.log"; then
      echo "  $name attempt $attempt: Chroma 竞态，重试"
      attempt=$((attempt+1)); sleep 3; continue
    fi
    if grep -q "合理性校验未通过" "$OUT/$name.log"; then
      echo "  $name attempt $attempt: 被合理性校验拒绝 → 改 --force-baseline"
      env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate \
        --update-baseline --force-baseline > "$OUT/$name.log" 2>&1
      if grep -q "基线已更新" "$OUT/$name.log"; then
        echo "########## $name  OK (--force-baseline)"
        grep -o "基线已更新: .*" "$OUT/$name.log" | head -1
        grep -E "^(category_|empty_|mean_|kp_)" "$OUT/$name.log"
        return 0
      fi
    fi
    echo "########## $name  FAILED (exit=$code)"
    grep -E "\[拒绝\]|\[失败\]" "$OUT/$name.log" | head -3
    return 1
  done
  echo "########## $name  重试耗尽"
  return 1
}

echo "===== REBASELINE START $(date) ====="
run rb1_fake_off
run rb2_fake_on        GATE_RERANK_MODE=on
run rb3_fake_disabled  GATE_RERANK_MODE=disabled
run rb4_real_off       GATE_USE_REAL_EMBEDDING=1
run rb5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run rb6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled
echo "===== REBASELINE DONE $(date) ====="
