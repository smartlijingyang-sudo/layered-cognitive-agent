"""Auto-generated surface skeleton for upstream ``sdk/server/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/server/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "Config",
    "JsonRpcConfig",
    "apply",
    "inject",
    "name",
]

Config = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from sdk/server/src/index.ts")

class JsonRpcConfig(Protocol):
    """Surface stub for upstream interface ``JsonRpcConfig``."""
    pass
