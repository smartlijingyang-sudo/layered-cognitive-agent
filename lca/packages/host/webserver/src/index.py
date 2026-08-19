"""Auto-generated surface skeleton for upstream ``host/webserver/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/webserver/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "WebRoute",
    "WebRouteKind",
    "WebServer",
    "WebUpgradeRoute",
]

WebRouteKind: TypeAlias = object  # port: surface stub

class WebServer:
    """Surface stub for upstream class ``WebServer``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WebServer.__init__ from host/webserver/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class WebRoute(Protocol):
    """Surface stub for upstream interface ``WebRoute``."""
    pass

class WebUpgradeRoute(Protocol):
    """Surface stub for upstream interface ``WebUpgradeRoute``."""
    pass
