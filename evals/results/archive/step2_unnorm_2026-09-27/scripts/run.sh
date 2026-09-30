#!/usr/bin/env bash
set -u
cd /c/Users/26452/Desktop/edu-agent || exit 1
OUT=/c/Users/26452/AppData/Local/Temp/edu_step1
PY=.venv/Scripts/python.exe

summarize() {
  local name="$1"
  echo "########## $name ##########"
  grep -E "kp_hit_at_k|kp_mrr|category_hit_at_1|category_hit_at_k|category_precision|empty_result_rate|mean_evidence_count|退化|通过|索引就绪|索引 .* 检索" "$OUT/$name.log" 2>/dev/null | head -25
  echo "exit_marker: $(grep -cE '退化' "$OUT/$name.log" 2>/dev/null) 条退化"
  echo ""
}

run() {
  local name="$1"; shift
  env "$@" PYTHONPATH=src "$PY" -m evaluation.retrieval_gate > "$OUT/$name.log" 2>&1
  local code=$?
  echo "$code" > "$OUT/$name.exit"
  summarize "$name"
  echo "exit=$code"
  echo ""
}

echo "===== START $(date) ====="

run r0_fake_off_unnorm     INGEST_SYNONYM_NORMALIZE=false RERANK_QUERY_NORMALIZE=false
run r1_fake_on             INGEST_SYNONYM_NORMALIZE=false RERANK_QUERY_NORMALIZE=false GATE_RERANK_MODE=on
run r2_fake_disabled       INGEST_SYNONYM_NORMALIZE=false RERANK_QUERY_NORMALIZE=false GATE_RERANK_MODE=disabled
run r3_real_off            INGEST_SYNONYM_NORMALIZE=false RERANK_QUERY_NORMALIZE=false GATE_USE_REAL_EMBEDDING=1
run r4_real_disabled       INGEST_SYNONYM_NORMALIZE=false RERANK_QUERY_NORMALIZE=false GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled

echo "########## r5_iso_expand_off (fake/off + expand 恒等) ##########"
env INGEST_SYNONYM_NORMALIZE=false RERANK_QUERY_NORMALIZE=false PYTHONPATH=src "$PY" -c "
import rag.recall as R
R.expand_query_with_synonyms = lambda q, max_expansions=8: q
from evaluation import retrieval_gate as G
raise SystemExit(G.main())
" > "$OUT/r5_iso_expand_off.log" 2>&1
echo "$?" > "$OUT/r5_iso_expand_off.exit"
summarize r5_iso_expand_off
echo "exit=$(cat "$OUT/r5_iso_expand_off.exit")"

echo "===== DONE $(date) ====="
