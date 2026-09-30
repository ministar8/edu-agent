"""量化「阈值 vs RRF 可达上限」的量纲错配：覆盖哪些查询类别。

纯算术（不需要索引）：把各类代表性 query 过一遍 `_resolve_retrieval_policy` 拿阈值，
再按 RRF 公式算可达上限（最高两条权重路由都命中时的分数和）。
"""

from __future__ import annotations

from rag.postprocess import _dynamic_rrf_k
from rag.query_classifier import classify_query
from rag.rag_utils import extract_query_terms, normalize_query_text
from rag.recall import ALL_ROUTES, get_route_weight
from rag.retriever import _resolve_retrieval_policy

K = 5
ROUTE_COUNT = 13  # 典型值：一次 L2/L3 查询实际跑的路由数
RRF_K = _dynamic_rrf_k(ROUTE_COUNT)

CASES = [
    ("短概念 (is_short)", "什么是死锁？"),
    ("一般 (default)", "进程的调度算法有哪些"),
    ("对比 (comparison)", "进程和线程的区别是什么？"),
    ("练习 (exercise)", "请出一道考查磁盘空闲空间管理的题。"),
    ("批改 (answer)", "学生的答案是：页面越大缺页率越低。请批改并说明理由。"),
    ("代码 (code)", "用信号量写出生产者—消费者问题的伪代码。"),
]

print(f"路由数 {ROUTE_COUNT} ⇒ _dynamic_rrf_k = {RRF_K}（标定公式隐含的是 k=20）")
print()
print(f"{'类别':22s} {'阈值':>8s} {'max_w':>7s} {'可达上限':>10s} {'判定':>14s}")
for label, q in CASES:
    cat = classify_query(q, extract_query_terms(normalize_query_text(q)))
    thr, _coarse = _resolve_retrieval_policy(q, K, 0.06, True, cat)

    weights = sorted((get_route_weight(r, cat) for r in ALL_ROUTES), reverse=True)
    top2 = weights[0] + weights[1]
    reachable = top2 / (RRF_K + 1)  # 两条最高权重路由都排第 1 时的分数和

    if thr > reachable:
        verdict = f"阈值 > 上限 ({thr - reachable:+.4f})"
    else:
        verdict = "ok"
    print(f"{label:22s} {thr:>8.4f} {weights[0]:>7.1f} {reachable:>10.4f} {verdict:>20s}")

print()
print("说明：「可达上限」= 两条最高权重路由都排第 1 时的 RRF 分数和。")
print("      超过它 ⇒ 任何文档都不可能过阈值，除非被 ≥3 条路由命中。")
