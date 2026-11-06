"""提示词服务层：对调用方暴露「变量准备 + 模板调用」的稳定入口。

模板内容仍在 `prompts.templates`，本包只负责调用前的变量整理，
避免各 Agent Node 各自复制一份格式化逻辑。
"""

from prompts.service.prompt_service import (
    MAX_QUESTION_COUNT,
    MIN_QUESTION_COUNT,
    NO_STANDARD_ANSWER,
    VALID_DIFFICULTIES,
    build_grade_messages,
    build_question_gen_messages,
)

__all__ = [
    "MAX_QUESTION_COUNT",
    "MIN_QUESTION_COUNT",
    "NO_STANDARD_ANSWER",
    "VALID_DIFFICULTIES",
    "build_grade_messages",
    "build_question_gen_messages",
]
