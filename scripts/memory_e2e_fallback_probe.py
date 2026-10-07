"""⑨ 组的**端到端**补充：兜底逻辑到底能不能被真实调用路径触发。

★ 为什么单独建一个脚本（2026-10-07，review 发现）
--------------------------------------------------
`memory_step4fix_gate.py` 的 ⑨d 系列**直接调** `_salvage_from_raw` / `_try_kv_dict`
—— 那是「函数级」断言：即使 `call_structured` 里那条兜底分支**根本走不到**，⑨d 照样全绿。
⑨e/⑨f 更弱，是 `inspect.getsource` 的**源码文本检查**。
⇒ 「护栏测的是函数、不是路径」是本项目反复踩到的同一类盲区。本脚本用**注入式假 LLM
驱动真实 `call_structured`**，并逐条打印**实际行为**（不写"应该怎样"）。

三种形态
--------
| # | 触发条件 | 兜底是否可达 |
|---|---|---|
| ① | 模型给出合法结构 → 正常返回对象 | 不需要 |
| ② | 抛 `ValidationError`（超长 + 工具标记污染，异常里带原文） | **应可达** —— 缺陷 A 的实测形态 |
| ③ | 返回 `None`（模型压根没发 tool call，裸文本没进 Pydantic） | 取决于实现 —— 本脚本**如实打印** |

③ 若不可达，是**已知盲区**而不是本脚本的失败：把它作为事实记录下来，供 Step 9 判断
是否需要叠加「产出后按 kp_index 语义匹配再落库」的兜底。

★ 同时做**反向验证**：把 `call_structured` 里的兜底调用整段摘掉，本脚本必须变红 ——
证明它测的是**路径**，不是又一个恒绿断言。

用法::

    PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_e2e_fallback_probe.py
    # 加 --reverse 做反向验证（期望退出码 1）

退出码：② 未被救回 ⇒ 1；③ 只披露，不参与判定。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import ValidationError  # noqa: E402

import rag.llm_calls as L  # noqa: E402
from schema.grading import GradingResult  # noqa: E402

# 缺陷 A 的真实形态：**多行** `key: value` + 混入工具标记（形状取自 Step 5 实测日志与 gate ⑨d）。
# ★ 兜底里的 `_try_kv_dict` 是**按行**扫描的 ⇒ 单行文本不是它的输入形态，
#   拿单行去测会得出"兜底不可达"的**假结论**（本脚本第一版就踩过）。
_MARK = "<parameter=x>"
_DIRTY_RAW = "\n".join(
    [
        "score: 40",
        "feedback: 结构描述基本正确，学生选 D 但正解是 B。" * 30 + f" {_MARK}",
        "is_wrong: true",
        "knowledge_points: 平衡二叉树, 平衡因子",
    ]
)


def _validation_error_on(raw: str) -> ValidationError:
    """造一个「异常里带着原文」的 ValidationError —— 与真实超长污染同形。

    把整段原文当作**该结构化的输入**送进校验 ⇒ Pydantic 报 `dict_type` 类错误，
    且 `errors()[i]["input"]` 就是原文本身，正是 `_raw_from_validation_error` 取回素材的路径。
    """
    try:
        GradingResult.model_validate(raw)
    except ValidationError as exc:
        return exc
    raise AssertionError("构造失败：model_validate(裸字符串) 本应抛 ValidationError")


class _StubBindable:
    """替代 `llm.with_structured_output(...)` 的返回值；按脚本给定的行为序列响应。"""

    def __init__(self, behaviors: list[object]) -> None:
        self._behaviors = behaviors
        self.calls = 0

    async def ainvoke(self, _prompt: object, config: object = None) -> object:
        b = self._behaviors[min(self.calls, len(self._behaviors) - 1)]
        self.calls += 1
        if isinstance(b, BaseException):
            raise b
        return b


async def _drive(behaviors: list[object], *, disable_salvage: bool = False) -> tuple[object, int]:
    """把假 LLM 塞进**真实**的 `call_structured`，返回 `(结果, 实际调用次数)`。"""
    stub = _StubBindable(behaviors)
    orig_bind = L._bind_structured
    orig_salv = L._salvage_from_raw
    L._bind_structured = lambda llm, schema: stub
    if disable_salvage:
        # 反向验证：把兜底整段摘掉 ⇒ ② 应当不再被救回
        L._salvage_from_raw = lambda raw, schema, stage: None
    try:
        out = await L.call_structured(
            [{"role": "human", "content": "批改这题"}],
            GradingResult,
            temperature=0.0,
            timeout=5,
            stage="e2e_probe",
        )
    finally:
        L._bind_structured = orig_bind
        L._salvage_from_raw = orig_salv
    return out, stub.calls


def main() -> int:
    reverse = "--reverse" in sys.argv
    good = GradingResult(score=40, feedback="概念对但选项错", is_wrong=True, error_analysis="混淆")
    print(
        f"STRUCTURED_OUTPUT_METHOD={L.settings.STRUCTURED_OUTPUT_METHOD} "
        f"RETRIES={L.settings.STRUCTURED_OUTPUT_RETRIES}（本脚本用注入式假 LLM，不发真实请求）"
    )

    ok = True

    # ── ① 正常路径：应一次成功、不触发兜底 ─────────────────────
    out1, calls1 = asyncio.run(_drive([good]))
    hit1 = isinstance(out1, GradingResult) and out1.score == 40
    print(
        f"  ① 合法结构          -> {'OK' if hit1 else 'BAD'} 结果={type(out1).__name__} 调用次数={calls1}"
    )
    ok &= hit1

    # ── ② ValidationError（缺陷 A 形态）：兜底**必须可达** ──────
    out2, calls2 = asyncio.run(_drive([_validation_error_on(_DIRTY_RAW)] * 3))
    salvaged = out2 is not None
    print(
        f"  ② 超长+标记污染      -> {'OK' if salvaged else 'BAD'} 被救回={salvaged} "
        f"结果={getattr(out2, 'score', None)} 调用次数={calls2}（含重试）"
    )
    print(f"     兜底产物 knowledge_points={getattr(out2, 'knowledge_points', None)}")
    if reverse:
        # 反向验证：摘掉兜底后，② 必须**不再**被救回，否则护栏是假的
        out2x, _ = asyncio.run(_drive([_validation_error_on(_DIRTY_RAW)] * 3, disable_salvage=True))
        teeth = out2x is None
        print(f"  ★ 反向验证：摘掉兜底后 ② 未被救回 = {teeth}（应为 True，否则本探针是恒绿的）")
        return 1 if teeth else 0
    ok &= salvaged

    # ── ③ 完全没发 tool call（返回 None）：只披露，不判定 ───────
    out3, calls3 = asyncio.run(_drive([None]))
    print(f"  ③ 无 tool call（None）-> 实际结果={out3!r} 调用次数={calls3}")
    print(
        "     ★ 这条是**已知盲区**：兜底要求拿到过原文，而 None 不产生原文 ⇒ "
        "该形态下裸文本无法被救回。是否为它加兜底，交 Step 9 依实测决定。"
    )

    print(f"\n判定：{'✅ ①② 行为符合预期' if ok else '❌ 兜底路径未按预期工作'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
