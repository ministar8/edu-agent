"""Evidence Chain 护栏的共享内核：判据计数器 + 跨判据共用夹具。

★ 原单文件 `evidence_chain_gate.py` 拆成「内核 + 判据组」若干模块。本模块持有唯一的
  可变状态 `_ITEMS`（判据计数器）与 `check()`，被各判据模块共同 import —— 计数器语义
  不变：`check()` 永远追加到**本模块**的 `_ITEMS`，facade 的 `main()` 读的是同一个对象。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
# ★ scripts/ 也要上路径：`check_6` 用 `import lib.build_claim_ledger`（lib/ 子包在 scripts/ 下）。
#   移位前靠 `sys.path[0]=scripts/` 隐式生效，进 gates/ 后失效 ⇒ 显式注入。
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

_EXPECTED_ITEMS = 81  # Task 7 结束 49；Task 8 Step 1（8a–8g）+7 = 56；T8-C/T8-E（8h/8i）+2 = 58
# ★ 修复轮 F7 再 +4：`8j`（map_route_failures 双向）/`8k`（单元内 reset 回归锁）/
#   `8l`（run_case 必调 reset_memory_read_statuses，**行为**取证）/`8m`（gate 的 reset↔收割配对）
#   ⇒ 62；控制器复验发现 F6 的映射只由外部探针证明、62 项里没有一条会因它回归而红
#   ⇒ 补 `8n`（缺键/空串/failed ⇒ missing_premise 的双向回归锁）⇒ 63；
#   checkpoint 8 用户追加 `8o`（F6 的**结构**承重锁 —— 8n 的四条行为用例分不出 `has_path`
#   与真值写法，因为那三条分支输出同为 `missing_premise` ⇒ 只能走 AST 定位函数体内调用）⇒ **64**；
#   Task 9 Step 1（B2 四态判据 9a/9b/9c/9d/9e）+5 ⇒ 69；阶段 A 后半段 B2 两条验收探针 `9f`
#   + B1 唯一权威换算点结构锁 `9g` +2 ⇒ 71；控制器复验 B2「产生→存储→聚合→报告」全链路时发现
#   `rerank_status` 要跨**三跳改名**才落到归档（`_rerank_status` → `rerank_status` → probe → record），
#   每跳都带 `""` 掩盖默认值、且桥接在 `aretrieve_documents` 内部（纯内存测试拿不到）⇒ 补 `9h`
#   键名配对结构锁 ⇒ **72**；
#   ★ 收尾修复批（Important-1/2/3）+7：`9j`（reprobe 的 B7 消费侧**行为**锁：注入故障 ⇒ error
#   不降级 + 凭据成对刷新 + 下一条干净 record 不受染）/`9k`（verify 缺键/空串/ok/error 四格
#   **行为**锁，钉死「缺键不得 pass」）/`9l`（`_no_reply` 体内 `has_path` 的 AST 承重锁，8o 同款）/
#   `9m`（空包送达**行为**锁：真实 aretrieve_documents 的 finally 出参 + 真实 retriever 桥接五格）/
#   `9n`（基线 payload 导出 `_meta.rerank_status_counts` **行为**锁）/`9o`（probe 读侧五格等值
#   **行为**锁）/`9p`（record 侧 probe⇒record⇒to_dict 工件送达**行为**锁）⇒ **79**；
#   ★ P−1 批 1（schema 与契约）+2：`9q`（`gold_answer_status`↔`gold_source_ref` 键集**双向**
#   相等 + 值域 + 「缺状态不得折成 present」的判据行为 + V0 五元组归因 + 缺字段/错键分开
#   统计）/`9r`（`_as_tri_bool` 三态 None/true/false 各一、false≠缺失，且 `incomplete_source`
#   ×`verdict_requires_figure` 三格按 §4.4.3 分流）⇒ **81**。
#   计数器只增不减：既有判据一条都不许删；`8g`/`8k` 的期望文件集随 reprobe 第三单元**按事实生长**
#   （不是放松 —— 单元内部 reset 的禁句 `8k` routes 零调用断言原样保留）。
_ITEMS: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    _ITEMS.append((label, bool(passed), detail))


def _gen_reply(
    *,
    stem: str = "题干：设 Cache 采用 2-Way 组相联，主存 64 块，Cache 8 行，问组号需要几位。",
    options: str = "A. 2\nB. 3\nC. 4\nD. 6",
    answer: str = "标准答案：B",
    explanation: str = "解析：8 行分 2 路，故 8/2=4 组，组号需 2 位……因此选 B。",
) -> str:
    """Task 5 的分段夹具：四段拼接，缺省全给（`falsify.apply` 逐段弄坏的原料）。"""
    parts = {"stem": stem, "options_or_task": options, "answer": answer, "explanation": explanation}
    return "\n\n".join(v for v in parts.values() if v)


def _base_record(**overrides: Any) -> dict:
    """falsify 的基线 record：四段齐全、答案键与解析结论**自洽**（都指 B）。"""
    rec = {
        "task": "generate",
        "case_id": "falsify-1",
        "reply": _gen_reply(),
        "top_items": [{"kp": ["co.overview"]}],
        "gold": {
            "gold_answer": "B",
            "gold_source_ref": {"gold_answer": "knowledge/co/ch3.md#组相联"},
            # ★ 合成夹具（P−1 批 1）：present 状态只存在于本判据代码，dataset/归档一律不填。
            #   没有它 ⇒ gen_correctness 按 §4.4.7-1 走 missing_premise、falsify 基线断链。
            "gold_answer_status": {"gold_answer": "present"},
            "expected_kp": ["co.overview"],
        },
        "item_reasons": {},
    }
    rec.update(overrides)
    return rec


def _falsify_all() -> dict[str, list[Any]]:
    """generate 每条判据 × 全部声明 mutation 的一次取证（check_5 与 --emit 共用）。"""
    from evaluation.task_eval import falsify
    from evaluation.task_eval.predicates import registry

    preds = registry.for_task("generate")
    out: dict[str, list[Any]] = {}
    for pred in preds:
        base = _base_record()
        siblings = {q.name: (q, base) for q in preds if q.name != pred.name}
        out[pred.name] = [
            falsify.evaluate(
                pred,
                base,
                falsify.apply(mutation=mut, record=base),
                mutation_input=mut["input"],
                siblings=siblings,
            )
            for mut in falsify.declared_mutations(pred)
        ]
    return out


def _gold(*, should: bool = True, values: tuple[str, ...] = ("平衡二叉树",)):
    """造一份可机械判定的 gold。

    已核实的真源：`cases.py:85` ⇒ `MEMORY_TYPES = frozenset({"weak_topics"})`（**只有一个合法值**，
    且 frozenset 不能下标取元素 —— 别写 `MEMORY_TYPES[0]`）；
    `cases.py:120` ⇒ 可机械判定要求 `type ∈ MEMORY_TYPES` ∧ `bool(values)` ∧ `should_be_recalled is not None`。
    """
    from evaluation.task_eval.cases import ExpectedAnswerProperty, ExpectedMemory, Gold

    return Gold(
        expected_memory=ExpectedMemory(
            type="weak_topics", values=list(values), should_be_recalled=should
        ),
        # ★ 偏差（Task 8 报告 D-1）：brief 原样是 `ExpectedAnswerProperty()`，并注释
        #   「全默认 ⇒ forbidden_values 为空 ⇒ correct ≡ used」。**实测不成立** ——
        #   `cases.py:134` 的默认是 `forbidden_values: list[str] | None = None`，
        #   而 `None` 的语义是**未标注**（`cases.py:131` 明写「必填（可为 []）」），
        #   ⇒ `ExpectedAnswerProperty().is_valid()` 为 False ⇒ `memory_mechanizable()` False
        #   ⇒ 8a/8b/8c 全拿到 None（实测 FAIL 过，见报告）。
        #   本夹具要的是「可机械判定的 gold」⇒ 显式传 `[]`（= 标注了「无禁止值」，
        #   此时 `correct ≡ used` 这条退化才真的成立）。
        expected_answer_property=ExpectedAnswerProperty(forbidden_values=[]),
    )
