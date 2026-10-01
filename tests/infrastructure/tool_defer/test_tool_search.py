"""Tests for ToolSearchTool (lca.infrastructure.tool_defer.tool_search)."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import Tool
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    reset_current_defer_session,
    set_current_defer_session,
)
from lca.infrastructure.tool_defer.tool_search import (
    ToolSearchTool,
    tool_search_factory,
)


class FakeTool:
    """Minimal structural Tool: name/description/parameters + execute."""

    def __init__(
        self,
        name: str,
        params: dict[str, Any] | None = None,
        namespace: str = "",
    ) -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"fake tool {name}"
        self.parameters = params or {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}


def _bound_session() -> tuple[ToolDeferSession, Any]:
    session = ToolDeferSession(DeferPolicy.default())
    tools = (
        FakeTool("tool_search", namespace="core"),
        FakeTool("b_one", namespace="web"),
        FakeTool("b_two", namespace="web"),
    )
    session.update_turn(tools)
    token = set_current_defer_session(session)
    return session, token


async def test_execute_loads_namespace_and_returns_specs() -> None:
    session, token = _bound_session()
    try:
        tool = ToolSearchTool()
        obs = await tool.execute({"namespace": "web"})
    finally:
        reset_current_defer_session(token)
    assert obs.success is True
    assert obs.payload["namespace"] == "web"
    assert [t["function"]["name"] for t in obs.payload["tools"]] == [
        "b_one",
        "b_two",
    ]
    assert session.loaded_namespaces == frozenset({"web"})


async def test_execute_without_session_returns_error_observation() -> None:
    tool = ToolSearchTool()
    obs = await tool.execute({"namespace": "web"})
    assert obs.success is False
    assert "no defer session" in (obs.error or "")


async def test_execute_unknown_namespace_returns_error_observation() -> None:
    _, token = _bound_session()
    try:
        obs = await ToolSearchTool().execute({"namespace": "nope"})
    finally:
        reset_current_defer_session(token)
    assert obs.success is False
    assert "nope" in (obs.error or "")
    # The error should help the agent recover: list what exists.
    assert "web" in (obs.error or "")


async def test_execute_blank_namespace_returns_error_observation() -> None:
    _, token = _bound_session()
    try:
        obs = await ToolSearchTool().execute({"namespace": ""})
    finally:
        reset_current_defer_session(token)
    assert obs.success is False


def test_validate() -> None:
    tool = ToolSearchTool()
    assert tool.validate({"namespace": "web"}) is None
    assert tool.validate({"namespaces": ["web", "file"]}) is None
    assert tool.validate({}) is not None
    assert tool.validate({"namespace": ""}) is not None
    assert tool.validate({"namespace": 42}) is not None
    assert tool.validate({"namespaces": []}) is not None
    assert tool.validate({"namespaces": [123]}) is not None


def test_implements_tool_protocol() -> None:
    tool = ToolSearchTool()
    assert isinstance(tool, Tool)
    assert tool.name == "tool_search"
    assert tool.is_idempotent is True
    assert "namespace" in tool.parameters["properties"]
    assert "namespaces" in tool.parameters["properties"]


def test_factory_returns_tool_instance() -> None:
    tool = tool_search_factory(object())
    assert isinstance(tool, ToolSearchTool)
