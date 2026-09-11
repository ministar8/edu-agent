"""针对假 checkpointer 的 /api/threads 单元测试。

只覆盖真实 checkpointer 难以按需触发的分支：行数/分页上限、过滤后仍返回越权行的
checkpointer、缺失时间戳、查询失败。过滤、排序、标题、子图线程这些真实数据库能验证的
行为放在 test_threads_sqlite.py 里用 SQLite 测。

与参考项目的差异：用户身份来自 JWT，路由按 token 中的用户 id 过滤并忽略入参 user_id。
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

DEFAULT_AGENT = "edu-assistant"


class FakeCheckpointTuple:
    def __init__(self, thread_id: str, checkpoint_id: str, checkpoint: dict, metadata: dict):
        self.config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
        self.checkpoint = checkpoint
        self.metadata = metadata


class FakeCheckpointer:
    """/api/threads 依赖的 checkpointer 语义。

    checkpoint 按 checkpoint_id 全局有序，alist 把 metadata 过滤当作精确匹配处理，
    每个 thread 的首个 checkpoint 写在 step -1（LangGraph 写 input checkpoint 的方式）。
    """

    def __init__(self):
        self.rows: list[FakeCheckpointTuple] = []
        self.alist_filters: list[dict | None] = []
        self._next_id = 0

    def _checkpoint_id(self) -> str:
        self._next_id += 1
        return f"cp-{self._next_id:06d}"

    def add_thread(
        self,
        thread_id: str,
        user_id: str,
        agent_id: str = DEFAULT_AGENT,
        turns: int = 1,
        title: str = "Hello",
        subgraph_heads: int = 0,
        tip_ts: str | None = "2024-07-31T20:14:19.804150+00:00",
    ) -> None:
        def add(step: int, channel_values: dict, ts: str | None) -> None:
            self.rows.append(
                FakeCheckpointTuple(
                    thread_id,
                    self._checkpoint_id(),
                    {"ts": ts, "channel_values": channel_values},
                    {"step": step, "user_id": user_id, "agent_id": agent_id},
                )
            )

        add(-1, {"__start__": {"messages": [HumanMessage(content=title)]}}, "2024-01-01T00:00:00Z")
        # 子图运行会写自己的 head，继承父运行的 metadata。
        for _ in range(subgraph_heads):
            add(-1, {"__start__": {}}, "2024-01-01T00:00:00Z")

        messages: list = []
        for turn in range(turns):
            messages = messages + [
                HumanMessage(content=title if turn == 0 else f"{title} {turn}"),
                AIMessage(content="reply"),
            ]
            add(
                turn * 2,
                {"messages": messages},
                tip_ts if turn == turns - 1 else "2024-01-01T00:00:01Z",
            )

    async def alist(self, config, *, filter=None, before=None, limit=None):
        self.alist_filters.append(filter)
        rows = sorted(self.rows, key=lambda r: r.config["configurable"]["checkpoint_id"])
        rows.reverse()
        yielded = 0
        for row in rows:
            if filter and any(row.metadata.get(key) != value for key, value in filter.items()):
                continue
            if (
                before
                and row.config["configurable"]["checkpoint_id"]
                >= (before["configurable"]["checkpoint_id"])
            ):
                continue
            yield row
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    async def aget_tuple(self, config):
        thread_id = config["configurable"]["thread_id"]
        rows = [r for r in self.rows if r.config["configurable"]["thread_id"] == thread_id]
        if not rows:
            return None
        return max(rows, key=lambda r: r.config["configurable"]["checkpoint_id"])


def test_threads_without_checkpointer_returns_empty(auth_user, test_client, mock_agent) -> None:
    """agent 未配置 checkpointer 时 /api/threads 应返回空列表。"""
    mock_agent.checkpointer = None

    response = test_client.get(
        "/api/threads",
        params={"user_id": str(auth_user.user_id), "limit": 10},
        headers=auth_user.headers,
    )

    assert response.status_code == 200
    assert response.json() == {"threads": []}


def test_threads_requires_auth(test_client) -> None:
    """未带凭证访问 /api/threads 应 401。"""
    response = test_client.get("/api/threads", params={"user_id": "u", "limit": 10})
    assert response.status_code == 401


@pytest.mark.parametrize("limit", [0, -1, 101, 999999])
def test_threads_rejects_out_of_range_limit(auth_user, test_client, mock_agent, limit: int) -> None:
    """limit 越界应 422，避免客户端要求无上限扫描。"""
    mock_agent.checkpointer = FakeCheckpointer()

    response = test_client.get(
        "/api/threads",
        params={"user_id": str(auth_user.user_id), "limit": limit},
        headers=auth_user.headers,
    )

    assert response.status_code == 422


def test_threads_skips_checkpoints_with_mismatched_metadata(
    auth_user, test_client, mock_agent
) -> None:
    """忽略 filter 的 checkpointer 也不能泄漏其他用户/agent 的线程。"""

    class LeakyCheckpointer(FakeCheckpointer):
        async def alist(self, config, *, filter=None, before=None, limit=None):
            async for row in super().alist(config, before=before, limit=limit):
                yield row

    uid = str(auth_user.user_id)
    checkpointer = LeakyCheckpointer()
    checkpointer.add_thread("thread-mine", user_id=uid, title="Mine")
    checkpointer.add_thread("thread-other-user", user_id="other-user", title="Other user")
    checkpointer.add_thread(
        "thread-other-agent", user_id=uid, agent_id="other-agent", title="Other agent"
    )
    checkpointer.add_thread("thread-no-metadata", user_id="", agent_id="", title="No metadata")
    mock_agent.checkpointer = checkpointer

    response = test_client.get(
        "/api/threads",
        params={"user_id": uid, "limit": 10},
        headers=auth_user.headers,
    )

    assert response.status_code == 200
    assert [t["thread_id"] for t in response.json()["threads"]] == ["thread-mine"]


def test_threads_pages_past_subgraph_heads(auth_user, test_client, mock_agent) -> None:
    """子图 head 行不应把真实线程挤出结果。

    带子图的 agent 每个线程会写多行 head，因此一页行数覆盖的线程数远少于请求数。
    """
    uid = str(auth_user.user_id)
    checkpointer = FakeCheckpointer()
    for index in range(30):
        checkpointer.add_thread(
            f"thread-{index:02d}", user_id=uid, title=f"Thread {index}", subgraph_heads=9
        )
    mock_agent.checkpointer = checkpointer

    with patch("service.threads.HEAD_PAGE_SIZE", 20):
        response = test_client.get(
            "/api/threads",
            params={"user_id": uid, "limit": 30},
            headers=auth_user.headers,
        )

    assert response.status_code == 200
    threads = response.json()["threads"]
    assert len(threads) == 30
    assert threads[0]["thread_id"] == "thread-29"


def test_threads_bounds_total_rows_scanned(auth_user, test_client, mock_agent) -> None:
    """head 分页应在上限处停止，而不是扫全表。"""
    uid = str(auth_user.user_id)
    checkpointer = FakeCheckpointer()
    for index in range(60):
        checkpointer.add_thread(
            f"thread-{index:02d}", user_id=uid, title=f"Thread {index}", subgraph_heads=9
        )
    mock_agent.checkpointer = checkpointer

    with (
        patch("service.threads.HEAD_PAGE_SIZE", 20),
        patch("service.threads.MAX_HEAD_ROWS", 100),
    ):
        response = test_client.get(
            "/api/threads",
            params={"user_id": uid, "limit": 30},
            headers=auth_user.headers,
        )

    assert response.status_code == 200
    assert len(checkpointer.alist_filters) == 5
    assert len(response.json()["threads"]) == 10


def test_threads_tolerates_missing_timestamp(auth_user, test_client, mock_agent) -> None:
    """tip checkpoint 无时间戳时 /api/threads 仍应返回该线程。"""
    uid = str(auth_user.user_id)
    checkpointer = FakeCheckpointer()
    checkpointer.add_thread("thread-no-ts", user_id=uid, title="No timestamp", tip_ts=None)
    mock_agent.checkpointer = checkpointer

    response = test_client.get(
        "/api/threads",
        params={"user_id": uid, "limit": 10},
        headers=auth_user.headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["threads"][0]["thread_id"] == "thread-no-ts"
    assert payload["threads"][0]["updated_at"] is None


def test_threads_checkpointer_error_returns_500(auth_user, test_client, mock_agent) -> None:
    async def broken_alist(*args, **kwargs):
        raise RuntimeError("db unavailable")
        yield  # pragma: no cover

    mock_agent.checkpointer = type("Checkpointer", (), {})()
    mock_agent.checkpointer.alist = broken_alist

    response = test_client.get(
        "/api/threads",
        params={"user_id": str(auth_user.user_id), "limit": 10},
        headers=auth_user.headers,
    )
    assert response.status_code == 500
