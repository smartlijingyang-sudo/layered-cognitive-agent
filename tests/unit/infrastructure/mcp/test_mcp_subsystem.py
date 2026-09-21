"""Tests for LCA MCP Infrastructure."""

import pytest

from lca.contracts.models.mcp.types import (
    MCPTransportType,
)
from lca.infrastructure.mcp.bridge import build_tools_from_mcp_manager
from lca.infrastructure.mcp.config import load_mcp_servers
from lca.infrastructure.mcp.manager import MCPManager


def test_mcp_config_loading():
    """Verify dedicated mcp.yaml parses correctly with env interpolation."""
    servers = load_mcp_servers()
    assert "exa" in servers
    assert "searxng" in servers

    exa_cfg = servers["exa"]
    assert exa_cfg.transport in (MCPTransportType.HTTP, MCPTransportType.STREAMABLE_HTTP)
    assert exa_cfg.url == "https://mcp.exa.ai/mcp"
    assert "x-api-key" in exa_cfg.headers

    searx_cfg = servers["searxng"]
    assert searx_cfg.transport == MCPTransportType.STDIO
    assert "searxng-mcp" in searx_cfg.command


def test_find_mcp_config_priority(tmp_path, monkeypatch):
    """Verify priority: LCA_MCP_CONFIG > cwd/.lca/mcp.yaml > ~/.lca/mcp.yaml."""
    from lca.infrastructure.mcp.config import find_mcp_config_path

    # 1. Environment variable override
    custom_cfg = tmp_path / "custom.yaml"
    custom_cfg.write_text("servers: {}")
    monkeypatch.setenv("LCA_MCP_CONFIG", str(custom_cfg))
    assert find_mcp_config_path() == custom_cfg.resolve()

    monkeypatch.delenv("LCA_MCP_CONFIG", raising=False)

    # 2. Cwd .lca/mcp.yaml
    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    lca_dir = cwd_dir / ".lca"
    lca_dir.mkdir()
    project_cfg = lca_dir / "mcp.yaml"
    project_cfg.write_text("servers: {}")

    monkeypatch.chdir(cwd_dir)
    assert find_mcp_config_path() == project_cfg.resolve()


@pytest.mark.asyncio
async def test_searxng_mcp_live_discovery():
    """Test live stdio discovery with local SearXNG MCP server."""
    servers = load_mcp_servers()
    searx_cfg = servers.get("searxng")
    if not searx_cfg:
        pytest.skip("SearXNG MCP not configured")

    manager = MCPManager({"searxng": searx_cfg})
    try:
        await manager.initialize()
        tools = manager.get_all_tools()
        assert len(tools) >= 1

        tool_names = [t.name for t in tools]
        assert "searxng_search" in tool_names

        # Verify bridge adaptation
        lca_tools = build_tools_from_mcp_manager(manager)
        assert len(lca_tools) >= 1
        qnames = [t.name for t in lca_tools]
        assert "mcp__searxng__searxng_search" in qnames

        res = await manager.execute_tool("searxng_search", {"query": "python"})
        assert not res.is_error
        assert len(res.text_content) > 0
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_stdio_transport_close_sync_marks_transport_closed():
    """Verify that close_sync properly terminates process and sets transport._closed."""
    from lca.infrastructure.mcp.transports.stdio import StdioMCPTransport

    servers = load_mcp_servers()
    searx_cfg = servers.get("searxng")
    if not searx_cfg:
        pytest.skip("SearXNG MCP not configured")

    transport = StdioMCPTransport(searx_cfg)
    await transport.connect()
    assert transport.is_connected
    assert transport._proc is not None
    internal_transport = getattr(transport._proc, "_transport", None)
    assert internal_transport is not None

    transport.close_sync()
    assert not transport.is_connected
    assert transport._proc is None
    # Underlying asyncio transport must be explicitly marked closed to prevent unraisable __del__ warning
    assert internal_transport._closed is True
