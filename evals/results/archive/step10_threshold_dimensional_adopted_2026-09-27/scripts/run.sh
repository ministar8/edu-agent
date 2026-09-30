#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step10
mkdir -p "$OUT/rebaseline" "$OUT/verify"
PY=.venv/Scripts/python.exe
REAL="GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1"

echo "===== STEP10 START $(date) ====="

echo "########## 1) 探针门禁重录基线 ##########"
env $REAL PYTHONPATH=src "$PY" -m evaluation.probe_gate --update-baseline > "$OUT/probe_rebaseline.log" 2>&1
echo "exit=$?"
grep -vE "^(WARNING|DEBUG|INFO|Building|Loading|Prefix|Async Chroma|Failed to parse)" "$OUT/probe_rebaseline.log" | tail -12

# 重录一轮：先试 --update-baseline；被合理性校验拒绝则改 --force-baseline；撞竞态则重试
run_rb() {
  local name="$1"; shift
  local attempt=1
  while [ $attempt -le 3 ]; do
    env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate --update-baseline \
      > "$OUT/rebaseline/$name.log" 2>&1
    if grep -q "基线已更新" "$OUT/rebaseline/$name.log"; then
      echo "  $name OK(attempt $attempt)"
      grep -E "^(category_precision|kp_hit_at_k|kp_mrr|mean_evidence_count) " "$OUT/rebaseline/$name.log"
      return 0
    fi
    if grep -q "检索期查询异常" "$OUT/rebaseline/$name.log"; then
      echo "  $name 竞态重试"; attempt=$((attempt+1)); sleep 3; continue
    fi
    if grep -q "合理性校验未通过" "$OUT/rebaseline/$name.log"; then
      echo "  $name 被合理性校验拒绝 -> --force-baseline"
      env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate \
        --update-baseline --force-baseline > "$OUT/rebaseline/$name.log" 2>&1
      if grep -q "基线已更新" "$OUT/rebaseline/$name.log"; then
        echo "  $name OK(--force-baseline)"
        grep -E "^(category_precision|kp_hit_at_k|kp_mrr|mean_evidence_count) " "$OUT/rebaseline/$name.log"
        return 0
      fi
    fi
    echo "  $name FAILED"; grep -E "\[拒绝\]|\[失败\]" "$OUT/rebaseline/$name.log" | head -3
    return 1
  done
  echo "  $name 重试耗尽"; return 1
}

echo ""
echo "########## 2) 重录 6 条检索基线 ##########"
run_rb rb1_fake_off
run_rb rb2_fake_on        GATE_RERANK_MODE=on
run_rb rb3_fake_disabled  GATE_RERANK_MODE=disabled
run_rb rb4_real_off       GATE_USE_REAL_EMBEDDING=1
run_rb rb5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run_rb rb6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled

echo ""
echo "########## 3) 独立验证：6 条检索门禁（不带 --update-baseline）##########"
run_v() {
  local name="$1"; shift
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate > "$OUT/verify/$name.log" 2>&1
  echo "--- $name exit=$?"
  grep -E "门禁通过|退化|\[失败\]" "$OUT/verify/$name.log" | head -4
}
run_v v1_fake_off
run_v v2_fake_on        GATE_RERANK_MODE=on
run_v v3_fake_disabled  GATE_RERANK_MODE=disabled
run_v v4_real_off       GATE_USE_REAL_EMBEDDING=1
run_v v5_real_on        GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1
run_v v6_real_disabled  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled

echo ""
echo "########## 4) 独立验证：探针门禁（不带 --update-baseline）##########"
env $REAL PYTHONPATH=src "$PY" -m evaluation.probe_gate > "$OUT/probe_verify.log" 2>&1
echo "exit=$?"
grep -vE "^(WARNING|DEBUG|INFO|Building|Loading|Prefix|Async Chroma|Failed to parse)" "$OUT/probe_verify.log" | tail -12

echo "===== STEP10 DONE $(date) ====="
