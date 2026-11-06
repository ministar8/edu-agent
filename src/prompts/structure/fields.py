"""统一结构规范：所有 **Agent Prompt** 必须遵守的 5 字段骨架。

适用范围：四个聊天 Agent（Supervisor / Knowledge / Question / Grading）的
静态 System Prompt。RAG 单轮模板与 service 结构化模板按各自任务形态设计，
不套用 5 字段（它们没有「角色/工具/示例」这类对话语义）。


[角色]  明确身份、职责和能力边界
[工具]  说明可用工具及调用时机
[规则]  规定决策逻辑、执行约束和禁止事项
[输出]  规定面向用户的输出格式与质量要求
[示例]  通过典型案例展示预期行为（可选）

Global Rules（来自 prompts.common）由各 Prompt 自行引用，不再强制统一拼接。
"""

FIELD_SCHEMA = {
    "角色": {
        "必填": True,
        "说明": "明确 Agent 身份、职责和能力边界。",
    },
    "工具": {
        "必填": True,
        "说明": "说明可用工具及调用时机。若无工具，明确写「无」。",
    },
    "规则": {
        "必填": True,
        "说明": "规定决策逻辑、执行约束和禁止事项。在此引用 prompts.common 的全局行为规则。",
    },
    "输出": {
        "必填": True,
        "说明": "规定面向用户的输出格式与质量要求。",
    },
    "示例": {
        "必填": False,
        "说明": "通过典型案例展示预期行为（Few-Shot），可选。",
    },
}

# 直接从 Schema 生成，避免重复维护；用 tuple 防止运行期意外修改
FIELD_ORDER: tuple = tuple(FIELD_SCHEMA.keys())

REQUIRED_FIELDS: tuple = tuple(
    name for name, spec in FIELD_SCHEMA.items() if spec["必填"]
)

__all__ = ["FIELD_SCHEMA", "FIELD_ORDER", "REQUIRED_FIELDS", "assemble_prompt"]


def assemble_prompt(
    role: str,
    tools: str,
    rules: str,
    output: str,
    examples: str = "",
) -> str:
    """统一的 Prompt 组装函数，按 5 字段顺序拼接。

    参数：
        role   ：[角色] 字段内容
        tools  ：[工具] 字段内容
        rules  ：[规则] 字段内容（已自行引入 prompts.common 所需规则）
        output ：[输出] 字段内容
        examples：[示例] 字段内容，可为空

    返回：
        组装后的纯字符串 Prompt，不含花括号。

    异常：
        ValueError：任何必填字段为空时抛出。
    """
    # 职责 2：检查必填字段
    provided = {
        "角色": role,
        "工具": tools,
        "规则": rules,
        "输出": output,
    }
    missing = [name for name in REQUIRED_FIELDS if not provided.get(name, "").strip()]
    if missing:
        raise ValueError(
            f"assemble_prompt 缺少必填字段：{', '.join(missing)}"
        )

    parts = [
        f"[角色]\n{role}",
        f"[工具]\n{tools}",
        f"[规则]\n{rules}",
        f"[输出]\n{output}",
    ]
    if examples and examples.strip():
        parts.append(f"[示例]\n{examples.strip()}")
    return "\n\n".join(parts)
