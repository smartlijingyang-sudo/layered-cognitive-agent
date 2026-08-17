"""Auto-generated surface skeleton for upstream ``mcp/mcp-client/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``mcp/mcp-client/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "McpResult",
    "ReconnectConfig",
    "ResolvedReconnectPolicy",
    "StdioConfig",
    "StreamableHttpConfig",
    "apply",
    "inject",
    "name",
]

Config: TypeAlias = object  # port: surface stub

McpResult: TypeAlias = object  # port: surface stub

ReconnectConfig: TypeAlias = object  # port: surface stub

ResolvedReconnectPolicy: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from mcp/mcp-client/src/index.ts")

class StdioConfig(Protocol):
    """Surface stub for upstream interface ``StdioConfig``."""
    pass

class StreamableHttpConfig(Protocol):
    """Surface stub for upstream interface ``StreamableHttpConfig``."""
    pass
