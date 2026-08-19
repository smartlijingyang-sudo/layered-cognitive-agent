"""Auto-generated surface skeleton for upstream ``client/ui-settings-plugins/src/client/web-search-card-controller.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-plugins/src/client/web-search-card-controller.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "WEB_SEARCH_NS",
    "WebSearchCardController",
    "WebSearchCardFace",
    "WebSearchCardState",
    "WebSearchSettings",
]

WEB_SEARCH_NS = None  # port: surface stub

class WebSearchCardController:
    """Surface stub for upstream class ``WebSearchCardController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WebSearchCardController.__init__ from client/ui-settings-plugins/src/client/web-search-card-controller.ts")

class WebSearchCardFace(Protocol):
    """Surface stub for upstream interface ``WebSearchCardFace``."""
    pass

class WebSearchCardState(Protocol):
    """Surface stub for upstream interface ``WebSearchCardState``."""
    pass

class WebSearchSettings(Protocol):
    """Surface stub for upstream interface ``WebSearchSettings``."""
    pass
