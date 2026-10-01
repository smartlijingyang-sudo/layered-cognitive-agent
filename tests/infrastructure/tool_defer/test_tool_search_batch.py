from __future__ import annotations

import pytest

from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import ToolDeferSession, set_current_defer_session
from lca.infrastructure.tool_defer.tool_search import ToolSearchTool


class FakeTool:
    def __init__(self, name: str, namespace: str) -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"fake {name}"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self, args):
        return {}


@pytest.mark.asyncio
async def test_tool_search_batch_loading() -> None:
    policy = DeferPolicy.default()
    session = ToolDeferSession(policy)
    tools = (
        FakeTool("tool_search", "core"),
        FakeTool("readFile", "file"),
        FakeTool("memory_search", "memory"),
    )
    session.update_turn(tools)
    token = set_current_defer_session(session)
    try:
        searcher = ToolSearchTool()
        obs = await searcher.execute({"namespaces": ["file", "memory"]})
        assert obs.success is True
        assert "file" in session.loaded_namespaces
        assert "memory" in session.loaded_namespaces
        assert len(obs.payload["tools"]) == 2
    finally:
        session._loaded.clear()
        from lca.infrastructure.tool_defer.session import reset_current_defer_session

        reset_current_defer_session(token)


def test_missing_namespace_fails_loud() -> None:
    policy = DeferPolicy.default()
    session = ToolDeferSession(policy)

    class BadTool:
        def __init__(self) -> None:
            self.name = "bad"
            self.description = "bad"
            self.parameters: dict[str, str] = {}

        async def execute(self, args):
            return {}

    with pytest.raises(ValueError, match="namespace"):
        session.update_turn((BadTool(),))  # type: ignore[arg-type]


def test_invalid_namespace_fails_loud() -> None:
    policy = DeferPolicy.default()
    session = ToolDeferSession(policy)
    with pytest.raises(ValueError, match="namespace"):
        session.update_turn((FakeTool("bad", "invalid_domain"),))
