import pytest

from client import AgentClient


@pytest.fixture
def agent_client():
    """已选好 agent、不拉 /info 的客户端。"""
    ac = AgentClient(base_url="http://test", get_info=False)
    ac.update_agent("edu-assistant", verify=False)
    return ac
