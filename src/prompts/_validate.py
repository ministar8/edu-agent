"""提示词模板的 import 期校验。

放在包内（而非测试里）是为了**启动即失败**：模板变量写错时服务根本起不来，
而不是等第一个请求打到那条路径才炸。

**局限（须知情）**：只能校验「模板声明的变量 == 登记表」，无法证明**调用点**已同步传参。
调用点是否更新仍靠人；但模板一改，登记表不匹配就会在 import 期直接报错，不会静默。
"""

from langchain_core.prompts import ChatPromptTemplate

_DRY_RUN_VALUE = "x"


def validate_template(
    template: ChatPromptTemplate,
    *,
    name: str,
    variables: set[str],
) -> None:
    """校验模板变量与登记一致，并空跑一次确保能正常组出消息。

    空跑这一遍同时能暴露花括号转义写错（例如 JSON 示例漏了 `{{ }}`）。
    """
    actual = set(template.input_variables)
    if actual != variables:
        raise ValueError(
            f"{name} 的变量与登记不一致：模板需要 {sorted(actual)}，登记为 {sorted(variables)}。"
            " 改模板后请同步调用点与本登记处。"
        )
    template.format_messages(**dict.fromkeys(actual, _DRY_RUN_VALUE))


def validate_static_prompt(text: str, *, name: str) -> None:
    """校验纯字符串提示词不含花括号。

    agent / supervisor 的 system prompt 是纯 `str`，由 `create_agent` /
    `create_supervisor` 直接使用，**不做任何格式化**。因此里面的 `{student_profile}`
    不会被填充，而是被当**字面文本**静默写进 system prompt —— 不报错、只是模型看到
    一个占位符。

    这里把它变成 import 期失败。若确实需要字面花括号（例如在 system prompt 里展示
    JSON 结构），说明它不该是纯字符串提示词，应改用 ChatPromptTemplate（有转义与校验）。
    """
    if "{" in text or "}" in text:
        raise ValueError(
            f"{name} 含花括号，但它是纯字符串提示词、不会被格式化 —— 花括号会被当字面文本"
            "发给模型。若你想注入变量，请改用 ChatPromptTemplate；若确实要字面花括号，"
            "请重新组织措辞。"
        )
