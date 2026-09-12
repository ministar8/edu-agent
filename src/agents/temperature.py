"""Agent 层 LLM 温度语义槽。

数值本身在 `core.settings`（可用环境变量覆盖）；这里只做**命名与归属**，
避免各 `*_agent.py` 散落魔数、后人不知为何批改用 0、出题用 0.3。
"""

from core import settings

# supervisor 路由：需要稳定分派，不宜过飘
TEMPERATURE_SUPERVISOR = settings.TEMP_DEFAULT

# 知识讲解：事实优先，默认即可
TEMPERATURE_KNOWLEDGE = settings.TEMP_DEFAULT

# 批改/评分：可复现、少发挥
TEMPERATURE_GRADING = settings.TEMP_PRECISE

# 聊天出题展示与结构化出题：需要题干多样性
TEMPERATURE_QUESTION = settings.TEMP_CREATIVE

# 检索链内部（分类/分解/HyDE 等）继续用 settings.TEMP_*，不经过本模块
