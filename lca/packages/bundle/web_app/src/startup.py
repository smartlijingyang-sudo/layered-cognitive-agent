"""Auto-generated surface skeleton for upstream ``bundle/web-app/src/startup.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``bundle/web-app/src/startup.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "WEB_STARTUP_SERVICE",
    "WebStartupValues",
    "apply",
    "inject",
    "name",
]

WEB_STARTUP_SERVICE = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from bundle/web-app/src/startup.ts")

class WebStartupValues(Protocol):
    """Surface stub for upstream interface ``WebStartupValues``."""
    pass
