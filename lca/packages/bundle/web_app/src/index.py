"""Auto-generated surface skeleton for upstream ``bundle/web-app/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``bundle/web-app/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "Config",
    "WebRuntimeValues",
    "apply",
    "inject",
    "internals",
    "name",
    "resolveLanTrust",
]

inject = None  # port: surface stub

internals = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from bundle/web-app/src/index.ts")

def resolveLanTrust(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveLanTrust``."""
    raise NotImplementedError("port resolveLanTrust from bundle/web-app/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class WebRuntimeValues(Protocol):
    """Surface stub for upstream interface ``WebRuntimeValues``."""
    pass
