"""模型标识与网关。

本项目区分两个**必须分开**的概念：

- **网关（Gateway）**：你实际调用的服务，决定 `base_url` 与 `api_key`。
- **模型 ID**：发给网关的 `model` 字段。

对外标识统一写成 ``<gateway>:<model_id>``：:

    dashscope:qwen3.7-max          # 通义千问，走阿里云百炼
    deepseek:deepseek-v4-flash     # DeepSeek 官方
    dashscope:deepseek-v4-flash    # 同一个 DeepSeek 模型，改走阿里云百炼

两家网关都是 OpenAI 兼容协议（所以可以共用同一个 ChatOpenAI 客户端），但
**base_url / api_key / 私有参数各不相同**。同一个模型 ID 可以出现在多个网关下，
因此网关必须显式写在标识里 —— **不能靠模型名去猜**。
"""

from enum import StrEnum, auto

MODEL_REF_SEPARATOR = ":"


class Gateway(StrEnum):
    """模型网关：决定 base_url 与 api_key。"""

    DASHSCOPE = auto()
    DEEPSEEK = auto()
    FAKE = auto()


# 各网关实际提供的模型 ID。新增模型时改这里即可（无需再维护一张「枚举 → 字符串」的表）。
GATEWAY_MODELS: dict[Gateway, frozenset[str]] = {
    # 阿里云百炼：自研 Qwen + 代理的 DeepSeek 模型
    Gateway.DASHSCOPE: frozenset(
        {"qwen3.7-max", "qwen3.6-27b", "deepseek-v4-flash", "deepseek-v4-pro"}
    ),
    # DeepSeek 官方：只有自家模型
    Gateway.DEEPSEEK: frozenset({"deepseek-v4-flash", "deepseek-v4-pro"}),
    # 测试用假模型
    Gateway.FAKE: frozenset({"fake"}),
}

# 每个网关的默认模型（多个网关同时启用时，按 Gateway 定义顺序取第一个可用的）
GATEWAY_DEFAULT_MODEL: dict[Gateway, str] = {
    Gateway.DASHSCOPE: "qwen3.7-max",
    Gateway.DEEPSEEK: "deepseek-v4-flash",
    Gateway.FAKE: "fake",
}


def make_model_ref(gateway: Gateway, model_id: str) -> str:
    """拼出对外使用的模型标识。"""
    return f"{gateway}{MODEL_REF_SEPARATOR}{model_id}"


def model_refs_for(gateway: Gateway) -> set[str]:
    """该网关上所有可用的模型标识。"""
    return {make_model_ref(gateway, model_id) for model_id in GATEWAY_MODELS[gateway]}


def parse_model_ref(ref: str) -> tuple[Gateway, str]:
    """把 ``<gateway>:<model_id>`` 解析成 (网关, 模型 ID)。

    未知网关会抛 ValueError —— 与其静默走错 base，不如直接报错。
    """
    gateway, separator, model_id = str(ref).partition(MODEL_REF_SEPARATOR)
    if not separator or not model_id:
        raise ValueError(f"模型标识需形如 <gateway>:<model_id>，收到: {ref!r}")
    return Gateway(gateway), model_id
