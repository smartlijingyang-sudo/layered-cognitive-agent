"""Auto-generated surface skeleton for upstream ``mcp/mcp-client/src/tools.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``mcp/mcp-client/src/tools.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "McpResult",
    "ToolBridgeOptions",
    "ToolDisposers",
    "publicToolName",
    "syncTools",
]

McpResult: TypeAlias = object  # port: surface stub

ToolDisposers: TypeAlias = object  # port: surface stub

def publicToolName(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``publicToolName``."""
    raise NotImplementedError("port publicToolName from mcp/mcp-client/src/tools.ts")

def syncTools(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``syncTools``."""
    raise NotImplementedError("port syncTools from mcp/mcp-client/src/tools.ts")

class ToolBridgeOptions(Protocol):
    """Surface stub for upstream interface ``ToolBridgeOptions``."""
    pass
