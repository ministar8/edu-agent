"""公共行为规则，各 Prompt 自行按需导入。

不再强制统一拼接为 GLOBAL_RULES。每个 Agent 根据自身职责，决定引入哪些规则：

| 规则 | 适用 Agent | 不适用 Agent | 说明 |
|------|-----------|-------------|------|
| `SAFETY_RULES` | 全部 4 个 Agent | 无 | 安全与合规底线（不得编造来源、不得敏感内容等） |
| `OUTPUT_FORMAT_RULES` | knowledge / question / grading | Supervisor | 输出面向用户文本的 Agent 需要（不得 Markdown 代码块、不得引导语） |
| `LENGTH_LIMIT_RULE` | knowledge / question / grading | Supervisor | 输出面向用户文本的 Agent 需要（字数控制） |
| `STRUCTURED_OUTPUT_RULE` | question / grading | Supervisor / knowledge | 需要结构化输出的 Agent（出题、批改） |
| `JSON_ONLY_RULE` | （暂无 Agent 使用） | 全部 | 仅在需要纯 JSON 输出时引入 |

Supervisor 作为路由主管，不输出面向用户文本，仅引入 `SAFETY_RULES` 作为底线，
不引入 `OUTPUT_FORMAT_RULES` 或 `LENGTH_LIMIT_RULE`，避免被强制套用不适合的规则。
"""

from prompts.common.safety import SAFETY_RULES
from prompts.common.output_format import OUTPUT_FORMAT_RULES
from prompts.common.length import LENGTH_LIMIT_RULE
from prompts.common.structured import STRUCTURED_OUTPUT_RULE, JSON_ONLY_RULE

__all__ = [
    "SAFETY_RULES",
    "OUTPUT_FORMAT_RULES",
    "LENGTH_LIMIT_RULE",
    "STRUCTURED_OUTPUT_RULE",
    "JSON_ONLY_RULE",
]
