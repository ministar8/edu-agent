"""Step 4 收尾 · 五项缺口修复的机械 Gate（**不跑 agent、零 LLM 成本**）。

验证 2026-10-06 定稿的五项修复**已实现且行为正确**：

    P0  ① `recalled` 脱离 judge —— 改由 harness 从记忆卡机械判定
    P0  ② `run_case` 真正接线 `run_sessions`（memory 任务走跨会话）
    P0  ③ Memory gold 两字段（expected_memory / expected_answer_property）
    P1  ④ checkpointer 跑后清理（finally）
    P1  ⑤ `MEMORY_CARD_MESSAGE_ID` 从产品导入（不再硬编码）

判据（全部可机械判定）：
    ①a harness 的 `MEMORY_CARD_MESSAGE_ID` **就是** 产品的同一对象（`is`）
    ①b `judge.apply_judge` 不再写 `memory_retrieved/used/correct`（护栏生效）
    ①c judge 的原判落到 `judge_memory_*` 诊断字段（可对照）
    ②a `runner._run_agent` 的签名接受 task/case_id
    ②b `task="memory"` 时确实调 `run_sessions`（猴补丁探测）
    ②c `task="qa"` 时仍走 `run_turns`（不误伤其他任务）
    ③a 合法 gold ⇒ 四问：recalled_pass / used / correct / N/A
    ③b **负样本**（should_be_recalled=false）实际未召回 ⇒ recalled_pass=True
    ③c gold 缺失 ⇒ 三项全 None（记 N/A，不退回 judge）
    ④a `_cleanup_threads` 存在且能删掉真实 thread
    ④b `run_sessions` 的清理在 `finally` 里（异常也清）
    ⑤a `gold_sanity` 对 memory 缺失 gold 报 ERROR
    ⑤b `gold_sanity` 对**非 canonical** 的 values 报 ERROR

Step 5 真跑暴露的 4 个产品缺陷，已各自的回归护栏（2026-10-06 追加）：

    ⑧ knowledge_points 示例名必须 canonical（缺陷 B）
    ⑨ 批改链路抗格式飘移（缺陷 A：feedback 截断 + 标记清洗 + 重试）
    ⑩ context-fallback（缺陷 C：工具拿不到 config ⇒ record_grade 被静默跳过）
    ⑪ `normalize_topic` 不得改坏 canonical name（缺陷 D）
    ⑫ `GRADE_PROMPT` 的词表与 `kp_index` 同源（缺陷 E · 方案 A，2026-10-07 E-4 追加）
    ⑬ 重判归因保全 / jsonl 尾换行 / 负样本前置条件（2026-10-07 review B 组）
    ㉓ 写入证据判据的位置 / 归因 / 下游（2026-10-08 review C1+I1+I3）

**判据数量本身也是判据**（2026-10-08 review I6）：`_EXPECTED_ITEMS` 声明总数，收尾比对实际
执行数（含 `skip()` 登记的「未执行」项）。少一项（某组提前 return、抛错被吞、改了没同步常量）
⇒ 退出码 1；有 `⏭ 未执行` ⇒ 同样不算「全绿」。背景：`⑬l/⑭d~f/⑱a~b/⑳d` 这 8 项读的是
`evals/results/task_eval/*.jsonl`，而按 D11 那些归档**不入库** ⇒ 干净克隆上它们会静默消失、
`main()` 却照样绿 —— 「175 项全绿」这句话在别的机器上其实只是「167 项跑过」。

用法::

    PYTHONPATH=src .venv/Scripts/python scripts/mem/memory_step4fix_gate.py
"""

from __future__ import annotations

import asyncio

import _m4f_core
from _m4f_checks_1_2 import check_1, check_2
from _m4f_checks_3 import check_3
from _m4f_checks_4_8 import check_4, check_4_real, check_5, check_6, check_7, check_8
from _m4f_checks_9_11 import check_9, check_10, check_11
from _m4f_checks_12_14 import check_12, check_13, check_14
from _m4f_checks_15_17 import check_15, check_16, check_17
from _m4f_checks_18_19 import check_18, check_19
from _m4f_checks_20_23 import check_20, check_21, check_22, check_23
from _m4f_checks_24_27 import check_24, check_25, check_26, check_27
from _m4f_checks_28_30 import check_28, check_29, check_30


def main() -> int:
    check_1()
    check_2()
    check_3()
    check_4()
    asyncio.run(check_4_real())
    check_5()
    check_6()
    check_7()
    check_8()
    check_9()
    asyncio.run(check_10())
    check_11()
    check_12()
    check_13()
    check_14()
    check_15()
    check_16()
    check_17()
    check_18()
    check_19()
    check_20()
    check_21()
    check_22()
    check_23()
    check_24()
    check_25()
    check_26()
    check_27()
    check_28()
    check_29()
    check_30()

    return _m4f_core.finish()


if __name__ == "__main__":
    raise SystemExit(main())
