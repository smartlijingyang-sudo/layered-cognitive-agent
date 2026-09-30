"""Tests for the pure MCP tool namespace-routing table."""

from lca.contracts.models.mcp.types import MCPTool
from lca.infrastructure.mcp.routing import build_tool_routing_table


def _tool(server_name: str, name: str) -> MCPTool:
    return MCPTool(server_name=server_name, name=name)


def test_qualified_names_always_routable():
    tools = [
        ("exa", _tool("exa", "web_search")),
        ("searxng", _tool("searxng", "searxng_search")),
    ]
    routing, collisions = build_tool_routing_table(tools)

    assert routing["mcp__exa__web_search"] == ("exa", tools[0][1])
    assert routing["mcp__searxng__searxng_search"] == ("searxng", tools[1][1])
    assert collisions == {}


def test_unambiguous_raw_name_is_routable():
    tools = [
        ("exa", _tool("exa", "web_search")),
        ("searxng", _tool("searxng", "searxng_search")),
    ]
    routing, collisions = build_tool_routing_table(tools)

    assert routing["web_search"] == ("exa", tools[0][1])
    assert routing["searxng_search"] == ("searxng", tools[1][1])
    assert collisions == {}


def test_colliding_raw_names_are_not_routed():
    tools = [
        ("exa", _tool("exa", "search")),
        ("searxng", _tool("searxng", "search")),
    ]
    routing, collisions = build_tool_routing_table(tools)

    assert "search" not in routing
    assert collisions["search"] == ["exa", "searxng"]
    # Qualified names remain routable despite the raw-name collision
    assert routing["mcp__exa__search"] == ("exa", tools[0][1])
    assert routing["mcp__searxng__search"] == ("searxng", tools[1][1])


def test_routing_is_deterministic():
    tools = [
        ("exa", _tool("exa", "search")),
        ("searxng", _tool("searxng", "search")),
    ]
    first, first_collisions = build_tool_routing_table(tools)
    second, second_collisions = build_tool_routing_table(tools)

    assert first == second
    assert first_collisions == second_collisions
