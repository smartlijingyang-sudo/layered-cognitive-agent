"""Auto-generated surface skeleton for upstream ``host/frontend-static/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/frontend-static/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "apply",
    "inject",
    "name",
    "serveStatic",
]

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from host/frontend-static/src/index.ts")

def serveStatic(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``serveStatic``."""
    raise NotImplementedError("port serveStatic from host/frontend-static/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
