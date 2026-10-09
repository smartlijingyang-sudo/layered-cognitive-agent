"""Pure namespace-routing table for MCP tools."""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.models.mcp.types import MCPTool


def build_tool_routing_table(
    tools: Iterable[tuple[str, MCPTool]],
) -> tuple[dict[str, tuple[str, MCPTool]], dict[str, list[str]]]:
    """Map lookup keys to the (server_name, tool) pair that hosts them.

    Every tool is addressable by its qualified name (``mcp__{server}__{tool}``).
    A raw tool name is also routable only when it is unambiguous across
    all servers; colliding raw names are excluded from the table and reported
    with the server names they appeared on.
    """
    routing: dict[str, tuple[str, MCPTool]] = {}
    raw_matches: dict[str, list[tuple[str, MCPTool]]] = {}
    collisions: dict[str, list[str]] = {}

    for server_name, tool in tools:
        routing[tool.qualified_name] = (server_name, tool)
        raw_matches.setdefault(tool.name, []).append((server_name, tool))

    for raw_name, matches in raw_matches.items():
        if len(matches) == 1:
            routing[raw_name] = matches[0]
        else:
            collisions[raw_name] = [server for server, _ in matches]

    return routing, collisions
