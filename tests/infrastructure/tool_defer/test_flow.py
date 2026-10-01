"""Defer-tool flow test: run entry → dispatch turn view → assemble render →
``tool_search`` load → re-render with full schemas.

Drives the seam the way the runtime does, without the heavy run
infrastructure:

* run entry (``lifecycle.py`` / ``execution_environment.py``):
  ``set_current_defer_session`` … ``finally`` ``reset_current_defer_session``
* ``concept.tool.fork`` dispatch: ``session.update_turn(items, namespaces)``
* ``think.history.assemble``: ``session.render_turn()`` → model-visible slice
* agent: ``ToolSearchTool.execute({"namespace": ...})`` → schemas from next turn
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    current_defer_session,
    reset_current_defer_session,
    set_current_defer_session,
)
from lca.infrastructure.tool_defer.tool_search import ToolSearchTool


class FakeTool:
    """Structural Tool: name / description / parameters."""

    def __init__(self, name: str, params: dict[str, Any] | None = None) -> None:
        self.name = name
        self.description = f"fake tool {name}"
        self.parameters = params or {"type": "object", "properties": {}}


def _wire_names(wire: tuple[dict[str, Any], ...]) -> list[str]:
    return [spec["function"]["name"] for spec in wire]


@pytest.mark.asyncio
async def test_full_defer_flow_run_to_render_to_load() -> None:
    """The whole defer loop as the runtime drives it, across two turns."""
    # --- run 入口: publish the session (what lifecycle.py does) ---
    token = set_current_defer_session(ToolDeferSession(DeferPolicy.default()))
    try:
        assert current_defer_session() is not None

        search = ToolSearchTool()
        items = [
            search,
            FakeTool("mcp_fs_read"),
            FakeTool("mcp_fs_write"),
            FakeTool("g2a_search"),
        ]
        # what ToolsService.tool_namespaces() records at fork_for_run
        namespaces = {
            "tool_search": "tool_search",
            "mcp_fs_read": "mcp",
            "mcp_fs_write": "mcp",
            "g2a_search": "g2a",
        }
        session = current_defer_session()
        assert session is not None

        # --- turn 1: dispatch refreshes the view, assemble renders ---
        session.update_turn(items, namespaces)
        wire, catalog = session.render_turn()

        # only the eager loader reaches the model; the rest are catalog lines
        assert _wire_names(wire) == ["tool_search"]
        assert "mcp" in catalog
        assert "g2a" in catalog
        # 目录只有一句话描述, 完整参数 schema 不能泄漏进来
        assert "parameters" not in catalog

        # --- agent reads the catalog and loads the mcp namespace ---
        obs = await search.execute({"namespace": "mcp"})
        assert obs.success is True
        assert [t["function"]["name"] for t in obs.payload["tools"]] == [
            "mcp_fs_read",
            "mcp_fs_write",
        ]

        # --- turn 2: dispatch refreshes (loaded set survives), assemble renders ---
        session.update_turn(items, namespaces)
        wire2, catalog2 = session.render_turn()
        names2 = _wire_names(wire2)

        assert "tool_search" in names2  # loader stays eager
        assert "mcp_fs_read" in names2
        assert "mcp_fs_write" in names2
        assert "g2a_search" not in names2  # still deferred
        assert "g2a" in catalog2
        assert "mcp" not in catalog2  # loaded namespaces leave the catalog

        # the full schema really arrived on the wire
        spec = next(s for s in wire2 if s["function"]["name"] == "mcp_fs_read")
        assert spec["function"]["parameters"] == {
            "type": "object",
            "properties": {},
        }
    finally:
        # --- run 出口: finally reset, never leaks into the next run ---
        reset_current_defer_session(token)

    assert current_defer_session() is None


def test_flow_without_session_falls_back_to_legacy() -> None:
    """No session (tests / legacy entries) → the audit invariant holds."""
    assert current_defer_session() is None
