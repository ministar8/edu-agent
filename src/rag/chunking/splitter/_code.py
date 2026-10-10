"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

import re

# 无围栏代码碎片的行首特征（讲义里大量 C/C++ 实例不写 ``` 围栏）
# ★ 刻意**不含**裸 `^\*`：C 块注释续行 `* ...` 与 Markdown 加粗 `**x**` / 无序列表 `* x`
#   行首同形，纯靠行首无法区分。408 讲义满是 `**识别信号**` 这类加粗标签，若保留该分支
#   会把整篇正文误判成代码（实测四科 ~90% chunk 被误加语义锚点）。块注释另有 `/*` 起点、
#   类型关键字等信号兜底，去掉 `^\*` 不损真实代码检出。
_CODE_FRAGMENT_START_RE = re.compile(
    r"^(?://|/\*|#include\b|#define\b|using\s+namespace\b"
    r"|void\s+\w+\s*\(|int\s+\w+\s*\(|bool\s+\w+\s*\(|char\s+\w+"
    r"|float\s+\w+|double\s+\w+|struct\s+\w+|class\s+\w+|template\s*<"
    r"|public:|private:|printf\s*\(|cout\s*<<|for\s*\(|while\s*\(|if\s*\()",
    re.MULTILINE,
)


def _looks_like_code_chunk(text: str, *, is_code_unit: bool = False) -> bool:
    """判断 chunk 是否应加语义锚点。

    不能只看 chunk 内是否残留 ```：围栏块被切开后，中间碎片可能一个围栏标记都没有却仍是
    纯代码。这类 chunk 缺中文语义，embedding/reranker 对中文 query 几乎无分。
    """
    if is_code_unit or "```" in text or "~~~" in text:
        return True
    stripped = text.lstrip()
    if _CODE_FRAGMENT_START_RE.search(stripped):
        return True
    # 极少中文且含典型代码符号 → 按代码对待
    han = len(re.findall(r"[一-鿿]", stripped))
    if han <= 2 and re.search(r"[{};]|->|::|\w+\s*\(", stripped):
        return True
    return False
