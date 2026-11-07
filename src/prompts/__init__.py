"""提示词统一入口：集中导出 + import 期校验。

顶层 __init__.py 的三个职责：
  1. 收集所有最终 Prompt（supervisor、agents、rag、service 等）。
  2. 调用 _validate.py 完成启动期校验：模板变量写错或纯字符串提示词里混进
     花括号，都会让服务启动失败，而不是等第一个请求打到那条路径才炸。
  3. 计算 PROMPT_SET_VERSION —— 全部提示词内容的 hash，随 trace metadata 上报，
     用于把「输出质量变化」归因到「提示词变化」。

按消费方分模块：
  - `prompts.supervisor`  Supervisor Prompt（路由主管，第1层纯字符串）
  - `prompts.agents`      三个专业 Agent Prompt + 结构化出题 Prompt（第1层纯字符串）
  - `prompts.templates`   Prompt 模板（第2层 ChatPromptTemplate：supervisor / 批改 / 出题）
  - `prompts.rag.retrieval` RAG 检索层单轮任务模板（ChatPromptTemplate）
  - `prompts.service`     提示词服务层（变量准备 + 模板调用）
  - `prompts.common`      公共行为规则（各 Prompt 自行按需导入，不强制统一拼接）
  - `prompts.structure`   统一结构规范（5 字段骨架 + 统一组装函数）
"""

import hashlib

from langchain_core.prompts import ChatPromptTemplate

from prompts._validate import validate_static_prompt, validate_template
from prompts.agents import (
    GRADING_AGENT_SYSTEM_PROMPT,
    KNOWLEDGE_AGENT_SYSTEM_PROMPT,
    QUESTION_AGENT_SYSTEM_PROMPT,
    QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT,
)
from prompts.common import (
    JSON_ONLY_RULE,
    LENGTH_LIMIT_RULE,
    OUTPUT_FORMAT_RULES,
    SAFETY_RULES,
    STRUCTURED_OUTPUT_RULE,
)
from prompts.rag import CLASSIFY_PROMPT, DECOMPOSE_PROMPT, HYDE_PROMPT
from prompts.supervisor import SUPERVISOR_PROMPT
from prompts.templates import (
    GRADE_PROMPT,
    QUESTION_GEN_PROMPT,
    SUPERVISOR_PROMPT_TEMPLATE,
)

__all__ = [
    "SAFETY_RULES",
    "OUTPUT_FORMAT_RULES",
    "LENGTH_LIMIT_RULE",
    "STRUCTURED_OUTPUT_RULE",
    "JSON_ONLY_RULE",
    "CLASSIFY_PROMPT",
    "DECOMPOSE_PROMPT",
    "GRADE_PROMPT",
    "GRADING_AGENT_SYSTEM_PROMPT",
    "HYDE_PROMPT",
    "KNOWLEDGE_AGENT_SYSTEM_PROMPT",
    "PROMPT_SET_VERSION",
    "QUESTION_AGENT_SYSTEM_PROMPT",
    "QUESTION_GEN_PROMPT",
    "QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT",
    "SUPERVISOR_PROMPT",
    "SUPERVISOR_PROMPT_TEMPLATE",
]

# 纯字符串提示词：无变量，但必须确保没人往里写了花括号（不会被格式化）
_STATIC_PROMPTS = {
    "prompts.agents.KNOWLEDGE_AGENT_SYSTEM_PROMPT": KNOWLEDGE_AGENT_SYSTEM_PROMPT,
    "prompts.agents.GRADING_AGENT_SYSTEM_PROMPT": GRADING_AGENT_SYSTEM_PROMPT,
    "prompts.agents.QUESTION_AGENT_SYSTEM_PROMPT": QUESTION_AGENT_SYSTEM_PROMPT,
    "prompts.agents.QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT": QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT,
    "prompts.supervisor.SUPERVISOR_PROMPT": SUPERVISOR_PROMPT,
}

# 带变量的模板 → 期望变量（集中登记；改模板必须同步这里）
_TEMPLATES: dict = {
    "prompts.rag.retrieval.HYDE_PROMPT": (HYDE_PROMPT, {"query", "max_chars"}),
    "prompts.rag.retrieval.CLASSIFY_PROMPT": (CLASSIFY_PROMPT, {"query"}),
    "prompts.rag.retrieval.DECOMPOSE_PROMPT": (DECOMPOSE_PROMPT, {"query", "max_subs"}),
    "prompts.templates.GRADE_PROMPT": (
        GRADE_PROMPT,
        {"stem", "standard_answer", "user_answer"},
    ),
    "prompts.templates.QUESTION_GEN_PROMPT": (
        QUESTION_GEN_PROMPT,
        {"count", "topic", "difficulty"},
    ),
    "prompts.templates.SUPERVISOR_PROMPT_TEMPLATE": (
        SUPERVISOR_PROMPT_TEMPLATE,
        {"messages"},
    ),
}

# ── 职责 2：调用 _validate.py 完成启动期校验 ──────────────────────
for _name, _text in _STATIC_PROMPTS.items():
    validate_static_prompt(_text, name=_name)

for _name, (_template, _variables) in _TEMPLATES.items():
    validate_template(_template, name=_name, variables=_variables)


def _template_source(template: ChatPromptTemplate) -> str:
    """取模板的原始文本（未渲染），用于计算版本 hash。"""
    parts = []
    for message in template.messages:
        prompt = getattr(message, "prompt", None)
        parts.append(getattr(prompt, "template", None) or str(message))
    return "\n".join(parts)


def _compute_prompt_set_version() -> str:
    """全部提示词内容的 hash —— 改任何一条，版本号就变。"""
    parts = [*_STATIC_PROMPTS.values()]
    parts += [_template_source(template) for template, _ in _TEMPLATES.values()]
    digest = hashlib.sha256("\n\x00\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


# 职责 3：计算 PROMPT_SET_VERSION
PROMPT_SET_VERSION = _compute_prompt_set_version()
