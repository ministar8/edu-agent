"""memory_step4fix_gate 的共享内核：计数器 + 判据登记原语（`check`/`skip`/`_flag`/`section`）。

★ 原单文件拆成「内核 + 判据组」。本模块持有**唯一**的可变状态（`_ok_all`/`_n_pass`/
  `_n_fail`/`_n_skip`）与登记原语，被各判据模块共同 import —— 计数语义不变：`check`/
  `skip`/`_flag` 永远改**本模块**的全局量，facade 的 `finish()` 读的也是同一批。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

_ok_all = True
_n_pass = 0
_n_fail = 0
_n_skip = 0

# ★ 判据总数必须**声明**出来（2026-10-08 review I6）。
#   背景：`⑬l×2 / ⑭d~⑭f / ⑱a~⑱b / ⑳d` 这 8 项读的是 `evals/results/task_eval/*.jsonl`，
#   而按 D11 的裁决那些归档**不入库** ⇒ 干净克隆上它们会静默消失，`main()` 照样打印
#   「GATE 通过 · exit 0」。于是文档与标签里那句「175 项全绿」在别的机器上其实是
#   「167 项跑过 + 8 项压根没跑」，两者根本不等价（这是「护栏全绿而它描述的路径不可达」
#   那一类的镜像：**绿灯的数量本身不可信**）。
#   ⇒ 加两个不变量：① 执行数（含跳过）必须等于本常量；② 跳过数必须为 0。
#      少跑一项、或某组提前 `return`，都在这里变红，而不是安静地少几行。
#   ★ 改判据时同步更新这个数（改完跑一次，末行会印实际值）。
_EXPECTED_ITEMS = 217  # Task 7 结束时 216；Task 8 Step 6 的 ⑱f（故障注入 ⇒ 三维 None）+1 = 217


def check(label: str, passed: bool, detail: str = "") -> None:
    global _ok_all, _n_pass, _n_fail
    mark = "✅" if passed else "❌"
    if not passed:
        _ok_all = False
        _n_fail += 1
    else:
        _n_pass += 1
    print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))


def skip(label: str, reason: str, count: int = 1) -> None:
    """显式登记「这一项**没跑**」—— 计数、并在收尾时把绿灯降级成红灯。

    ★ 与 `check(..., True)` 的区别：跳过**不是**通过。旧写法只 `print` 一行 `⏭`，
      不进任何计数 ⇒ 总数悄悄变小而退出码仍为 0（正是 I6）。
    `count`：一个 `if` 挡掉多项判据时用它（如 ⑭d~⑭f = 3 项）。
    """
    global _n_skip
    _n_skip += count
    print(f"  ⏭ {label} ×{count}：{reason}")


def _flag(message: str) -> None:
    """收尾阶段的失败判据（不参与计数：计数本身正是它检查的对象）。"""
    global _ok_all
    _ok_all = False
    print(f"  ❌ {message}")


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _gold(should: bool, vals: list[str], forb: list[str]):
    from evaluation.task_eval.cases import Gold

    return Gold.from_dict(
        {
            "expected_memory": {
                "type": "weak_topics",
                "values": vals,
                "should_be_recalled": should,
            },
            "expected_answer_property": {"forbidden_values": forb},
            # ★ setup_conditions 自 2026-10-06 Step 5 起为**必填**（case-validity），
            #   故 gate 的 fixture 也必须带上，否则 ⑤c 会被 setup_conditions 的 ERROR 干扰。
            "setup_conditions": {"min_grade_calls": 2},
        }
    )


def finish() -> int:
    """收尾：比对「执行数 == 声明数」且「无跳过」，打印总结并返回退出码。"""
    total = _n_pass + _n_fail + _n_skip
    print()
    print("=" * 72)
    print(
        f"判定项 {total} = 通过 {_n_pass} · 失败 {_n_fail} · 未执行 {_n_skip}"
        f"（声明值 {_EXPECTED_ITEMS}）"
    )
    if total != _EXPECTED_ITEMS:
        _flag(
            f"判据总数 {total} ≠ 声明的 {_EXPECTED_ITEMS} —— "
            "要么某组提前 return/抛错吞掉了后续项，要么改了判据没同步常量"
        )
    if _n_skip:
        _flag(f"有 {_n_skip} 项**未执行** ⇒ 本次不能称为「全绿」，只能说「跑了的那几项绿」")
    if _ok_all and total == _EXPECTED_ITEMS:
        print(
            "✅ STEP 4/5 GATE 通过 —— 五项修复 + case-validity + paired control "
            "+ KP 规范名 + 批改抗飘移 + context-fallback + topic 归一 + 写入证据判据均就位"
        )
    else:
        print("❌ STEP 4/5 GATE 未通过")
    print("=" * 72)
    if _ok_all and total == _EXPECTED_ITEMS and not _n_skip:
        print("★ 遗留：A→B 真跨 thread 召回（真跑 agent）属 Step 5 实跑，需消耗 token。")
    return 0 if (_ok_all and total == _EXPECTED_ITEMS and not _n_skip) else 1
