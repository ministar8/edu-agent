"""运行时基础设施：agent 装配与工具，不承载业务编排。

依赖方向：本包 → `rag` / `schema` / `core` / `prompts` / `memory`。
**禁止**顶层 import `specialists` / `orchestration`（避免环）。
出题/批改工具在函数内延迟 import 真源。
"""
