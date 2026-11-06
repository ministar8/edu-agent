"""编排层：教学图生命周期、内层 supervisor、状态 Schema、检索上下文。

依赖方向：本包 → `specialists`（经 supervisor）、`runtime`、`memory`、`core`。
**禁止** `specialists` / `runtime` 反向 import 本包。
"""

from agents.orchestration.teaching_graph import edu_supervisor

__all__ = ["edu_supervisor"]
