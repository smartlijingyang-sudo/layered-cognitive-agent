"""Auto-generated surface skeleton for upstream ``acp/acp/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``acp/acp/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AcpConfig",
    "Config",
    "apply",
    "inject",
    "name",
]

Config = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from acp/acp/src/index.ts")

class AcpConfig(Protocol):
    """Surface stub for upstream interface ``AcpConfig``."""
    pass
