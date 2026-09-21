"""Ambient MCP Tools builder for gateway and default toolset."""

from __future__ import annotations

import asyncio
import concurrent.futures

import structlog

from lca.contracts.protocols import Tool
from lca.infrastructure.mcp.bridge import build_tools_from_mcp_manager
from lca.infrastructure.mcp.config import find_mcp_config_path, load_mcp_servers
from lca.infrastructure.mcp.manager import MCPManager

_log = structlog.get_logger(__name__)

_AMBIENT_MCP_MANAGER: MCPManager | None = None


def get_ambient_mcp_manager() -> MCPManager | None:
    """Return shared ambient MCPManager instance if mcp.yaml exists."""
    global _AMBIENT_MCP_MANAGER
    if _AMBIENT_MCP_MANAGER is not None:
        return _AMBIENT_MCP_MANAGER

    config_path = find_mcp_config_path()
    if not config_path:
        return None

    try:
        servers = load_mcp_servers(config_path)
        if not servers:
            return None
        _AMBIENT_MCP_MANAGER = MCPManager(servers)
        return _AMBIENT_MCP_MANAGER
    except Exception as exc:
        _log.warning("ambient_mcp_manager_init_failed", error=str(exc))
        return None


async def reset_ambient_mcp_manager_async() -> None:
    """Asynchronously reset and close the cached ambient MCP manager."""
    global _AMBIENT_MCP_MANAGER
    if _AMBIENT_MCP_MANAGER is not None:
        mgr = _AMBIENT_MCP_MANAGER
        _AMBIENT_MCP_MANAGER = None
        await mgr.close()


def reset_ambient_mcp_manager() -> None:
    """Reset the cached ambient MCP manager (useful for tests and loop changes)."""
    global _AMBIENT_MCP_MANAGER
    if _AMBIENT_MCP_MANAGER is not None:
        mgr = _AMBIENT_MCP_MANAGER
        _AMBIENT_MCP_MANAGER = None
        mgr.close_sync()


async def _init_transient_and_disconnect(mgr: MCPManager) -> None:
    """Initialize manager on transient loop then disconnect transports to prevent leaks."""
    await mgr.initialize()
    for client in mgr._clients.values():
        await client._transport.close()


async def build_ambient_mcp_tools_async() -> list[Tool]:
    """Asynchronously discover and adapt all configured MCP tools."""
    manager = get_ambient_mcp_manager()
    if manager is None:
        return []

    try:
        if not manager.get_all_tools():
            await manager.initialize()
        return build_tools_from_mcp_manager(manager)
    except Exception as exc:
        _log.warning("build_ambient_mcp_tools_async_failed", error=str(exc))
        return []


def build_ambient_mcp_tools() -> list[Tool]:
    """Discover and adapt all configured MCP tools into native LCA Tool instances."""
    manager = get_ambient_mcp_manager()
    if manager is None:
        return []

    try:
        # Check if already initialized
        if not manager.get_all_tools():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # Running inside an event loop on current thread: run init in worker thread
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _init_transient_and_disconnect(manager))
                    future.result(timeout=30)
            else:
                asyncio.run(_init_transient_and_disconnect(manager))

        return build_tools_from_mcp_manager(manager)
    except Exception as exc:
        _log.warning("build_ambient_mcp_tools_failed", error=str(exc))
        return []
