"""针对真实 SQLite checkpointer 的 /api/threads 集成测试。

test_threads.py 用假 checkpointer 驱动，抓不到"数据库会拒绝的 metadata 过滤"或
"LangGraph 实际并不成立的 head-checkpoint 假设"。这里改跑真图 + 真 checkpointer。

与参考项目的差异：edu-agent 只有单 agent（DEFAULT_AGENT = edu-assistant），
路由为 /api/threads，身份来自 JWT；function-API 与 AG-UI 用例已删除。
由于 agent_id 恒为同一值，用不同用户来区分"普通图"与"子图"两组线程。
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, MessagesState, StateGraph

from db import init_db
from service import app

DEFAULT_AGENT = "edu-assistant"


async def echo(state: MessagesState) -> MessagesState:
    return {"messages": [AIMessage(content=f"echo: {state['messages'][-1].content}")]}


def build_graph_agent(checkpointer):
    graph = StateGraph(MessagesState)
    graph.add_node("echo", echo)
    graph.set_entry_point("echo")
    graph.add_edge("echo", END)
    return graph.compile(checkpointer=checkpointer)


def build_subgraph_agent(checkpointer):
    """调用带 checkpointer 的子图，形态与 supervisor agent 一致。"""
    inner = StateGraph(MessagesState)
    inner.add_node("echo", echo)
    inner.set_entry_point("echo")
    inner.add_edge("echo", END)

    outer = StateGraph(MessagesState)
    outer.add_node("worker", inner.compile())
    outer.set_entry_point("worker")
    outer.add_edge("worker", END)
    return outer.compile(checkpointer=checkpointer)


async def run_turns(agent, thread_id: str, user_id: str, messages: list[str]) -> None:
    config = RunnableConfig(
        configurable={"thread_id": thread_id},
        metadata={"user_id": user_id, "agent_id": DEFAULT_AGENT},
    )
    for message in messages:
        await agent.ainvoke({"messages": [HumanMessage(content=message)]}, config=config)


async def _register(client: httpx.AsyncClient, prefix: str) -> tuple[dict, str]:
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/auth/register", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, str(body["user"]["id"])


@pytest_asyncio.fixture
async def seeded(tmp_path):
    """种三个用户：A 走普通图，B 走子图，C 无任何线程（用于隔离断言）。"""
    # ASGITransport 不会触发 lifespan，手动建表以补齐
    init_db()

    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.db")) as checkpointer:
        graph_agent = build_graph_agent(checkpointer)
        subgraph_agent = build_subgraph_agent(checkpointer)

        transport = httpx.ASGITransport(app=app)
        with patch("service.service.get_agent", side_effect=lambda agent_id: graph_agent):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                headers_a, user_a = await _register(client, "alice")
                headers_b, user_b = await _register(client, "bob")
                headers_c, user_c = await _register(client, "carol")

                for thread_id, messages in {
                    "g-single": ["only turn"],
                    "g-multi": ["first turn", "second", "third"],
                }.items():
                    await run_turns(graph_agent, thread_id, user_a, messages)

                for thread_id, messages in {
                    "s-single": ["sub only turn"],
                    "s-multi": ["sub first turn", "sub second"],
                }.items():
                    await run_turns(subgraph_agent, thread_id, user_b, messages)

                yield SimpleNamespace(
                    client=client,
                    headers_a=headers_a,
                    user_a=user_a,
                    headers_b=headers_b,
                    user_b=user_b,
                    headers_c=headers_c,
                    user_c=user_c,
                    checkpointer=checkpointer,
                )


async def _list_threads(seeded, headers: dict, user_id: str, limit: int = 20) -> list[dict]:
    response = await seeded.client.get(
        "/api/threads", params={"user_id": user_id, "limit": limit}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["threads"]


@pytest.mark.asyncio
async def test_threads_lists_single_and_multi_turn_threads(seeded) -> None:
    """单轮线程不会越过 head checkpoint，但仍必须能被列出。"""
    threads = await _list_threads(seeded, seeded.headers_a, seeded.user_a)

    assert [t["thread_id"] for t in threads] == ["g-multi", "g-single"]
    assert [t["title"] for t in threads] == ["first turn", "only turn"]
    assert all(t["updated_at"] for t in threads)


@pytest.mark.asyncio
async def test_threads_isolates_users(seeded) -> None:
    a = sorted(t["thread_id"] for t in await _list_threads(seeded, seeded.headers_a, seeded.user_a))
    b = sorted(t["thread_id"] for t in await _list_threads(seeded, seeded.headers_b, seeded.user_b))
    c = await _list_threads(seeded, seeded.headers_c, seeded.user_c)

    assert a == ["g-multi", "g-single"]
    assert b == ["s-multi", "s-single"]
    assert c == []


@pytest.mark.asyncio
async def test_threads_lists_subgraph_threads_once(seeded) -> None:
    """子图运行会在嵌套命名空间下写自己的 head checkpoint，且继承父运行的 metadata。

    若不按 thread 去重就会被重复列出，并各付一次 tip 查询代价。
    """
    tip_lookups: list[str] = []
    original = AsyncSqliteSaver.aget_tuple

    async def counting_aget_tuple(self, config):
        tip_lookups.append(config["configurable"]["thread_id"])
        return await original(self, config)

    with patch.object(AsyncSqliteSaver, "aget_tuple", counting_aget_tuple):
        threads = await _list_threads(seeded, seeded.headers_b, seeded.user_b)

    assert [t["thread_id"] for t in threads] == ["s-multi", "s-single"]
    assert [t["title"] for t in threads] == ["sub first turn", "sub only turn"]
    assert sorted(tip_lookups) == ["s-multi", "s-single"]


@pytest.mark.asyncio
async def test_threads_orders_by_most_recent_update(seeded) -> None:
    """回复最旧的线程应把它顶到列表最前。"""
    before = await _list_threads(seeded, seeded.headers_a, seeded.user_a)
    assert before[-1]["thread_id"] == "g-single"

    response = await seeded.client.post(
        "/api/invoke",
        json={"message": "a later reply", "thread_id": "g-single"},
        headers=seeded.headers_a,
    )
    assert response.status_code == 200, response.text

    after = await _list_threads(seeded, seeded.headers_a, seeded.user_a)
    assert [t["thread_id"] for t in after] == ["g-single", "g-multi"]


@pytest.mark.asyncio
async def test_threads_respects_limit(seeded) -> None:
    threads = await _list_threads(seeded, seeded.headers_a, seeded.user_a, limit=1)
    assert [t["thread_id"] for t in threads] == ["g-multi"]


@pytest.mark.asyncio
async def test_history_returns_full_conversation(seeded) -> None:
    response = await seeded.client.post(
        "/api/history", json={"thread_id": "g-multi"}, headers=seeded.headers_a
    )
    assert response.status_code == 200, response.text
    messages = response.json()["messages"]
    assert [m["type"] for m in messages] == ["human", "ai"] * 3
    assert messages[0]["content"] == "first turn"


@pytest.mark.asyncio
async def test_history_rejects_other_users_thread(seeded) -> None:
    """thread_id 等同 bearer capability：拿到别人的 id 也不能读其会话。"""
    response = await seeded.client.post(
        "/api/history", json={"thread_id": "g-multi"}, headers=seeded.headers_c
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invoke_rejects_other_users_thread(seeded) -> None:
    """同样不能通过 /api/invoke 向别人的会话追加内容。"""
    response = await seeded.client.post(
        "/api/invoke",
        json={"message": "hijack", "thread_id": "g-multi"},
        headers=seeded.headers_c,
    )
    assert response.status_code == 404
