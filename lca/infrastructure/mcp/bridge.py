"""MCPToolBridge — Adapts MCP tools into LCA native Tool Protocol instances."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.mcp.types import MCPTool
from lca.contracts.protocols import Tool
from lca.contracts.protocols.act.tool.pipeline import ToolDefinition
from lca.infrastructure.mcp.manager import MCPManager


def adapt_mcp_tool_to_lca(manager: MCPManager, mcp_tool: MCPTool) -> Tool:
    """Build a first-class LCA Tool from an MCPTool declaration."""
    tool_name = mcp_tool.qualified_name
    description = mcp_tool.description or f"MCP tool '{mcp_tool.name}' on server '{mcp_tool.server_name}'"
    parameters = mcp_tool.input_schema or {"type": "object", "properties": {}}

    async def execute(_self: Tool, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        res = await manager.execute_tool(mcp_tool.qualified_name, args)
        latency_ms = res.latency_ms or int((time.monotonic() - start) * 1000)

        text = res.text_content
        is_success = not res.is_error

        return Observation(
            observation_id=new_id("obs"),
            success=is_success,
            payload=text if is_success else None,
            error=text if not is_success else None,
            latency_ms=latency_ms,
            extra={
                "mcp_server": mcp_tool.server_name,
                "mcp_tool": mcp_tool.name,
                "structured_content": res.structured_content,
            },
        )

    tool_cls = type(
        f"MCPTool_{mcp_tool.server_name}_{mcp_tool.name}",
        (Tool,),
        {
            "name": tool_name,
            "description": description,
            "parameters": parameters,
            "is_idempotent": False,
            "default_timeout_s": 60,
            "execute": execute,
        },
    )
    return tool_cls()  # type: ignore[no-any-return]


def adapt_mcp_tool_to_definition(mcp_tool: MCPTool) -> ToolDefinition:
    """Convert an MCPTool into an LCA ToolDefinition (for declarative / schema projection)."""
    return ToolDefinition(
        name=mcp_tool.qualified_name,
        description=mcp_tool.description,
        parameters=mcp_tool.input_schema or {"type": "object", "properties": {}},
        result_schema=mcp_tool.output_schema or {},
        is_idempotent=False,
        default_timeout_ms=60_000,
    )


def build_tools_from_mcp_manager(manager: MCPManager) -> list[Tool]:
    """Export all healthy MCP tools as LCA Tool instances."""
    return [adapt_mcp_tool_to_lca(manager, t) for t in manager.get_all_tools()]
