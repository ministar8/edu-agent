"""提示词统一入口：集中导出 + import 期校验。

按消费方分模块：
  - `agents.py`     三个专业 agent 的 system prompt（纯 str，供 create_agent）
  - `supervisor.py` 多 agent 分派 prompt（纯 str，供 create_supervisor）
  - `rag.py`        RAG 层单轮任务模板（ChatPromptTemplate）
  - `service.py`    service 层出题与批改模板（ChatPromptTemplate）

**导入本包即触发校验**（见 `_validate.py`）：模板变量写错或纯字符串提示词里混进
花括号，都会让服务启动失败，而不是等第一个请求打到那条路径才炸。

另外导出 `PROMPT_SET_VERSION` —— 全部提示词内容的 hash，随 trace metadata 上报，
用于把「输出质量变化」归因到「提示词变化」。
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
from prompts.rag import CLASSIFY_PROMPT, DECOMPOSE_PROMPT, HYDE_PROMPT, RELEVANCE_PROMPT
from prompts.service import GRADE_PROMPT, QUESTION_GEN_PROMPT
from prompts.supervisor import SUPERVISOR_PROMPT

__all__ = [
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
    "RELEVANCE_PROMPT",
    "SUPERVISOR_PROMPT",
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
_TEMPLATES: dict[str, tuple[ChatPromptTemplate, set[str]]] = {
    "prompts.rag.HYDE_PROMPT": (HYDE_PROMPT, {"query", "max_chars"}),
    "prompts.rag.CLASSIFY_PROMPT": (CLASSIFY_PROMPT, {"query"}),
    "prompts.rag.DECOMPOSE_PROMPT": (DECOMPOSE_PROMPT, {"query", "max_subs"}),
    "prompts.rag.RELEVANCE_PROMPT": (RELEVANCE_PROMPT, {"query", "evidence_list"}),
    "prompts.service.GRADE_PROMPT": (
        GRADE_PROMPT,
        {"stem", "standard_answer", "user_answer"},
    ),
    "prompts.service.QUESTION_GEN_PROMPT": (
        QUESTION_GEN_PROMPT,
        {"count", "topic", "difficulty"},
    ),
}

# ── 集中校验：写错 → import 期直接报错 ──────────────────────
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


PROMPT_SET_VERSION = _compute_prompt_set_version()
