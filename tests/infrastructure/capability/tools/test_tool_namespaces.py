"""Tests for ToolsService.tool_namespaces (defer-tool seam)."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.cognition.boundary import BindingsView
from lca.infrastructure.capability.tools.tools import ToolsService


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"fake {name}"
        self.parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}


def test_tool_namespaces_empty_on_definition_service() -> None:
    assert ToolsService().tool_namespaces() == {}


def test_fork_records_tool_namespaces() -> None:
    svc = ToolsService()
    svc.register_factory("solo", lambda b: FakeTool("solo_tool"))
    svc.register_factory("multi", lambda b: [FakeTool("m1"), FakeTool("m2")])
    svc.register_factory("empty", lambda b: None)
    svc.register(FakeTool("legacy_tool"))
    forked = svc.fork_for_run(BindingsView())
    assert forked.tool_namespaces() == {
        "solo_tool": "solo",
        "m1": "multi",
        "m2": "multi",
        "legacy_tool": "legacy_tool",
    }


def test_tool_namespaces_returns_a_copy() -> None:
    svc = ToolsService()
    svc.register_factory("solo", lambda b: FakeTool("solo_tool"))
    forked = svc.fork_for_run(BindingsView())
    mapping = forked.tool_namespaces()
    mapping["solo_tool"] = "tampered"
    assert forked.tool_namespaces()["solo_tool"] == "solo"
