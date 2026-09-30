"""反向验证：故意制造一个已知退化，确认探针门禁**真的会变红**。

做法：把 `_COLLECTION_KEYWORDS` 猴补丁还原成「单字收窄之前」的形态
（DS 收回单字 `串`/`图`，OS 去掉 `位示图`），其余一律不动。
预期：`#19` 由 `survived` 退化为 `not_recalled`（OS 不再被检索），门禁退出码 1。

★ 为什么用猴补丁而不是改文件：不触碰工作区，零回退风险；
  而门禁观测的是**行为**，猴补丁制造的行为退化与文件级退化等价。
"""

from __future__ import annotations

import sys

import rag.recall as R

NEW_DS = ("主串", "子串", "字符串匹配", "图的", "图论", "无向图", "有向图", "邻接表")
NEW_OS = ("位示图",)

kw: dict[str, tuple[str, ...]] = {}
for col, kws in R._COLLECTION_KEYWORDS.items():
    kw[col] = tuple(k for k in kws if k not in NEW_DS and k not in NEW_OS)
kw["data_structure"] = kw["data_structure"] + ("串", "图")
R._COLLECTION_KEYWORDS = kw

print("[反向验证] 已把词表还原成「改动前」：")
print("  位示图 的推断 ->", R._infer_subject_collections("位示图法是怎么工作的？"))
print()

from evaluation.probe_gate import main  # noqa: E402  （必须在猴补丁之后导入）

code = main([])
print()
print(f"[反向验证] 探针门禁退出码 = {code}（期望 1 = 抓到退化）")
sys.exit(0 if code == 1 else 1)
