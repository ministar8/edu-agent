"""#27 / D12(B) 的效果实测：**一次检索、两套读数**（零 LLM 调用，只打本地 TEI）。

为什么必须成对读
----------------
`kp_hit` 的 8 条 generate `coverage` N/A（0B/Phase 1 两份归档里都是同一批
`gen-002/003/005/006/008/009/012/014`）此前只有两个候选解释：
①「当时索引未打完标签」；② **#27**：`layer_recall` 的 top-up 路径把
`knowledge_points` 写死成 `[]`（而 `metadata` 里带着 JSON 字符串）⇒ 某题 top-5 若全走
top-up，`_all_kp(top)=[]` ⇒ 判 N/A。

要分辨二者，不能用「归档 vs 现在重跑」—— 那中间隔着索引状态与检索配置的变化，
变化量不止一个。⇒ 在**同一次** `probe_retrieval` 里对每条证据同时记两套读数：

    old = list(ev.knowledge_points)                 # 修复前评测看到的样子
    new = retrieval_probe._to_item(ev).knowledge_points   # 修复后（metadata 兜底解析）

其余一切（query、索引、融合、截断、gold）完全相同 ⇒ 差异只能来自读数本身。

口径边界（引用这个数字时必须一起说）
------------------------------------
- 本脚本只读本地 TEI，**不调用任何 LLM**。
- 重排是否生效取决于 `settings.RERANK_ENABLED`（本机为 `false` ⇒ 会被降级并打日志）。
  ⇒ 这是「同一次检索的两套读数」，**不是**与 0B 归档的可比复现。
- 结论只能写成：该机制**有能力**单独造成 N/A；不能写成「当时那 8 条就是这么来的」
  （归档没存 `evidence_id`/`top_items`，逐条溯源不可能 —— 见 §20.5.1 与 #27）。

用法::

    PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/kp_paired_reading_probe.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "src")

import evaluation.task_eval.retrieval_probe as rp  # noqa: E402
from evaluation.task_eval import metrics  # noqa: E402
from evaluation.task_eval.cases import load_demo  # noqa: E402

logger = logging.getLogger("kp_paired")

# (old_kps, new_kps) —— 每条证据在**同一次**检索里的两套读数
_pairs: list[tuple[list[str], list[str]]] = []
_orig_to_item = rp._to_item


def _spy_to_item(ev):
    """包装真实 `_to_item`：既产出修复后的 item，也记下修复前的读数。"""
    item = _orig_to_item(ev)
    _pairs.append((list(ev.knowledge_points or []), list(item.knowledge_points or [])))
    return item


async def run(tasks: tuple[str, ...] = ("generate", "qa")) -> dict[str, int]:
    """对每个有 `expected_kp` 的 case 做一次探针，返回两套读数的汇总。"""
    cases = [c for t in tasks for c in load_demo(t)]
    cases = [c for c in cases if c.gold.expected_kp]
    agg = {"n": 0, "na_old": 0, "na_new": 0, "cmp_old": 0, "cmp_new": 0, "hit_old": 0, "hit_new": 0}
    rescued: list[str] = []
    still_na: list[str] = []
    for c in cases:
        _pairs.clear()
        # ★ 修复批 Important-1 的三调用方判定：本脚本**不需要** `query_failures` 消费侧，
        #   理由是**有意**的，不是遗漏：
        #   ① 它不落任何归档工件 —— 探针返回值直接被丢弃，只消费 `_to_item` 间谍记下的
        #      **同一次检索内的两套 KP 读数**（old vs new），没有 `retrieval_status` 状态位
        #      可以被写错或降级，消费侧规则（`map_route_failures`）在这里没有作用对象。
        #   ② 成对读数的口径是「同一 query、同一索引、同一融合包」——若某条路由故障，
        #      两套读数**同等地**受影响，配对比较本身不失真；失真的是「索引健康」这类
        #      绝对结论，而本脚本的 docstring/打印早已自我限定为「机制的量级」，
        #      从不声称健康度。⇒ 按「不许顺手改成消费」，这里刻意不加 reset/消费。
        #   若将来把它升级为可归档的取证件（写 record），必须先接上 runner 同款消费侧。
        await rp.probe_retrieval(c.query, task_mode=c.task_mode, k=5, use_rerank=True)
        old_kps = [kp for o, _n in _pairs for kp in o]
        new_kps = [kp for _o, n in _pairs for kp in n]
        na_old, na_new = (not old_kps), (not new_kps)
        agg["n"] += 1
        agg["na_old"] += int(na_old)
        agg["na_new"] += int(na_new)
        if not na_old:
            agg["cmp_old"] += 1
            agg["hit_old"] += int(bool(metrics.kp_coverage(c.gold.expected_kp, old_kps)))
        if not na_new:
            agg["cmp_new"] += 1
            agg["hit_new"] += int(bool(metrics.kp_coverage(c.gold.expected_kp, new_kps)))
        if na_old and not na_new:
            rescued.append(c.case_id)
        elif na_old and na_new:
            still_na.append(c.case_id)
    agg["rescued"] = len(rescued)  # type: ignore[assignment]
    print(f"N/A→可判 的 case：{rescued}")
    print(f"两套读数下都仍然 N/A：{still_na}")
    return agg


async def main() -> int:
    rp._to_item = _spy_to_item  # 必须在探针之前换掉
    agg = await run()
    old_rate = agg["hit_old"] / agg["cmp_old"] if agg["cmp_old"] else float("nan")
    new_rate = agg["hit_new"] / agg["cmp_new"] if agg["cmp_new"] else float("nan")
    print()
    print(f"有 expected_kp 的 case：{agg['n']} 条")
    print(
        f"  coverage N/A（整批无 KP 标签）：修复前 {agg['na_old']} 条 → 修复后 {agg['na_new']} 条"
    )
    print(f"  可比对：{agg['cmp_old']} 条 → {agg['cmp_new']} 条")
    print(
        f"  kp_hit：{agg['hit_old']}/{agg['cmp_old']} = {old_rate:.3f} → "
        f"{agg['hit_new']}/{agg['cmp_new']} = {new_rate:.3f}"
    )
    print()
    print(
        "> 这张表说明的是**机制的量级**：同一次检索下，读数方式能单独把 12 条 case 变成 N/A。"
        "它**不**证明 0B 归档那 8 条当年就是这么来的（归档无 `evidence_id`，逐条溯源不可能）。"
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(asyncio.run(main()))
