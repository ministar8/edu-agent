"""对比改动前后 real/on 的「未命中目标学科」清单，定位具体是哪条 query 变了。"""

from __future__ import annotations

import re

BEFORE = r"C:\Users\26452\AppData\Local\Temp\edu_step1\v5_real_on.log"
AFTER = r"C:\Users\26452\AppData\Local\Temp\edu_step3\gate\g5_real_on.log"


def miss(path: str) -> tuple[int, list[str]]:
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"首条未命中目标学科的查询（(\d+) 条）：(.*?)(?:\n\n|\n路由)", text, re.S)
    if not m:
        return -1, []
    items = [ln.strip() for ln in m.group(2).splitlines() if ln.strip().startswith("-")]
    return int(m.group(1)), items


def norm(items: list[str]) -> set[str]:
    return {" ".join(i.split()) for i in items}


nb, ib = miss(BEFORE)
na, ia = miss(AFTER)
sb, sa = norm(ib), norm(ia)

print(f"BEFORE 未命中 {nb} 条 / AFTER 未命中 {na} 条")
print()
print("=== 新增未命中（改动后出现、改动前没有）===")
for x in sorted(sa - sb):
    print("  +", x[:90])
print()
print("=== 修复（改动前未命中、改动后命中）===")
for x in sorted(sb - sa):
    print("  -", x[:90])
