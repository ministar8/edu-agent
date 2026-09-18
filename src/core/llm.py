"""LLM 工厂：整合 DashScope/DeepSeek 的思考模式处理，提供两类入口。

- get_model(model_ref, temperature): agent 层使用，model_ref 形如 ``<gateway>:<model_id>``
- get_llm(streaming, temperature): RAG 检索链使用，模型来自 settings.LLM_MODEL

两条入口共用一份缓存，键为 ``(gateway, model_id, temperature, streaming)``。
"""

from __future__ import annotations

import logging
import re

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_openai import ChatOpenAI

from core.cache import BoundedCache
from core.settings import settings
from schema.models import Gateway, parse_model_ref

logger = logging.getLogger(__name__)


class FakeToolModel(FakeListChatModel):
    """支持 bind_tools 的假模型，用于测试。

    注意：本模型**有状态**（responses 队列会被消费，且耗尽后静默循环复用），
    因此绝不能进缓存 —— 共享实例会让多个 agent 的响应互相穿插。详见 core.cache 文档。
    """

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def _is_qwen3(model: str) -> bool:
    return "qwen3" in (model or "").lower()


def _is_qwen3_max(model: str) -> bool:
    return bool(re.search(r"qwen[\d.]+-max", (model or "").lower()))


# 缓存键 = 网关 + 模型 ID + 温度 + 是否流式。
# - **必须含网关**：同一个模型 ID 可以走不同网关（如 dashscope:deepseek-v4-flash 与
#   deepseek:deepseek-v4-flash），不含网关会让两家的客户端互相串用
# - 含 streaming → agent 层恒 True、RAG 层多为 False，行为不同必须区分
type LlmCacheKey = tuple[str, str, float, bool]

# 实际用量 = 模型数 × 温度（常量）× streaming，上限设 64 几乎不会触发淘汰。
_MAX_CACHED_CLIENTS = 64


def _close_llm_client(model: ChatOpenAI) -> None:
    """淘汰时释放客户端，避免 httpx 连接池随缓存项一起泄漏。

    已知限制：langchain-openai 的异步客户端是懒建的，关闭需要 ``await aclose()``，
    而淘汰发生在同步路径里无法 await —— 这里只关同步客户端，异步池交给 GC 兜底。
    """
    client = getattr(model, "root_client", None)
    if client is None:
        return
    try:
        client.close()
    except Exception:
        logger.debug("关闭被淘汰的 LLM 客户端失败", exc_info=True)


# 缓存只存真实客户端（假模型走早返回，永不入库）
_LLM_CACHE: BoundedCache[LlmCacheKey, ChatOpenAI] = BoundedCache(
    max_size=_MAX_CACHED_CLIENTS, name="llm", on_evict=_close_llm_client
)


def reset_llm_cache(*, notify: bool = False) -> None:
    """清空 LLM 缓存，仅用于测试隔离（本项目不需要配置热更新）。

    notify=False 时不触发 on_evict —— 测试中客户端通常从未真正建立过连接。
    """
    _LLM_CACHE.clear(notify=notify)


def _build_client(
    model_ref: str, model_id: str, temperature: float, *, streaming: bool
) -> ChatOpenAI:
    """构建 ChatOpenAI，并按厂商注入思考模式参数。"""
    api_base = settings.api_base_for_model(model_ref)

    extra_body: dict = {}
    # 以网关为准判断厂商；URL 字符串可能不含 "dashscope"（例如 MaaS 自定义域名）
    gateway = parse_model_ref(model_ref)[0]
    is_deepseek = gateway is Gateway.DEEPSEEK
    is_dashscope = gateway is Gateway.DASHSCOPE
    is_qwen3_max = _is_qwen3_max(model_id)

    # DeepSeek / Qwen3.x：默认禁用思考模式（reasoning token 暴增输出费用）
    if (is_deepseek or _is_qwen3(model_id)) and not (is_qwen3_max and is_dashscope):
        if is_deepseek:
            extra_body["thinking"] = {"type": "disabled"}
        else:
            extra_body["enable_thinking"] = False

    # Qwen3.x-max 思考模型通过 DashScope 必须 enable_thinking=True
    if is_qwen3_max and is_dashscope:
        extra_body["enable_thinking"] = True

    kwargs: dict = dict(
        api_key=settings.api_key_for_model(model_ref),
        base_url=api_base,
        model=model_id,
        temperature=temperature,
        streaming=streaming,
        request_timeout=settings.LLM_TIMEOUT,
        max_retries=2,
    )
    if extra_body:
        kwargs["extra_body"] = extra_body

    return ChatOpenAI(**kwargs)


def _cached_client(model_ref: str, temperature: float, *, streaming: bool) -> ChatOpenAI:
    """按 (网关, 模型 ID, 温度, streaming) 单飞获取客户端，两条入口共用。"""
    gateway, model_id = parse_model_ref(model_ref)
    return _LLM_CACHE.get_or_create(
        (gateway, model_id, temperature, streaming),
        lambda: _build_client(model_ref, model_id, temperature, streaming=streaming),
    )


def get_model(
    model_ref: str | None = None, /, temperature: float | None = None
) -> ChatOpenAI | FakeToolModel:
    """获取 LLM 实例（单飞缓存），agent 层使用。

    model_ref 形如 ``<gateway>:<model_id>``；缺省用 ``settings.DEFAULT_MODEL``。
    """
    if model_ref is None:
        model_ref = settings.DEFAULT_MODEL

    temp = settings.TEMP_DEFAULT if temperature is None else temperature

    # 假模型刻意不进缓存：FakeToolModel 有状态，共享会让响应互相穿插（见 core.cache 文档）
    if parse_model_ref(model_ref)[0] is Gateway.FAKE:
        return FakeToolModel(responses=["This is a test response from the fake model."])

    return _cached_client(model_ref, temp, streaming=True)


def get_llm(streaming: bool = False, temperature: float = 0.3) -> ChatOpenAI | FakeToolModel:
    """基于 ``settings.LLM_MODEL`` 获取 LLM 实例（RAG 检索链使用）。

    默认非流式 —— 与全部 RAG 调用点一致；需要流式时显式传 ``streaming=True``。

    ``LLM_MODEL`` 指向 fake 网关时返回 ``FakeToolModel``（与 ``get_model`` 同款处理）。

    **为什么必须补这个分支**：本函数此前直接走 ``_cached_client``，**没有 fake 分支**，
    而 ``get_model``（agent 层）有。后果是 ``USE_FAKE_MODEL=true`` 只让 agent 层变假，
    RAG 检索链仍去构造真实客户端：

    - 本地 ``.env`` 配了真实 key 时 → **真的调用线上模型**。检索链的 decompose / HyDE
      用温度 0.3，于是"评测"结果每次不同且产生费用 —— 基线失去可复现性。
    - CI 无 key 时 → ``openai.OpenAIError: Missing credentials`` 直接抛出，
      实测 40 条门禁 query 里有 6 条因此崩溃（异常一路穿透到
      ``aretrieve_evidence_with_retry`` 之外）。

    ``FakeToolModel`` 无法满足 structured output，因此 ``call_structured_*`` 会返回 None、
    检索链回落到规则路径 —— 这正是无外部依赖评测想要的行为。
    """
    # 与 get_model 同理：FakeToolModel 有状态（responses 队列会被消费），不进缓存
    if parse_model_ref(settings.LLM_MODEL)[0] is Gateway.FAKE:
        return FakeToolModel(responses=["This is a test response from the fake model."])
    return _cached_client(settings.LLM_MODEL, temperature, streaming=streaming)
