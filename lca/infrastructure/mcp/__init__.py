"""MCP (Model Context Protocol) Infrastructure for Layered Cognitive Agent."""

from lca.infrastructure.mcp.bridge import (
    adapt_mcp_tool_to_definition,
    adapt_mcp_tool_to_lca,
    build_tools_from_mcp_manager,
)
from lca.infrastructure.mcp.client import MCPClient
from lca.infrastructure.mcp.config import find_mcp_config_path, load_mcp_servers
from lca.infrastructure.mcp.manager import MCPManager

__all__ = [
    "MCPClient",
    "MCPManager",
    "adapt_mcp_tool_to_definition",
    "adapt_mcp_tool_to_lca",
    "build_tools_from_mcp_manager",
    "find_mcp_config_path",
    "load_mcp_servers",
]
