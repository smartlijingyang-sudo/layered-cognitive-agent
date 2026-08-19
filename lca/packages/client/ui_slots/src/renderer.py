"""Auto-generated surface skeleton for upstream ``client/ui-slots/src/renderer.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-slots/src/renderer.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "HostObservable",
    "LocaleFace",
    "RenderOpts",
    "SessionMaybeProvideInfo",
    "SessionProvideInfo",
    "SlotOwnershipError",
    "SlotRenderer",
    "SlotRendererHost",
    "StaleAuthorizationError",
    "StoreInstanceLike",
]

class SlotOwnershipError:
    """Surface stub for upstream class ``SlotOwnershipError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SlotOwnershipError.__init__ from client/ui-slots/src/renderer.ts")

class StaleAuthorizationError:
    """Surface stub for upstream class ``StaleAuthorizationError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port StaleAuthorizationError.__init__ from client/ui-slots/src/renderer.ts")

class HostObservable(Protocol):
    """Surface stub for upstream interface ``HostObservable``."""
    pass

class LocaleFace(Protocol):
    """Surface stub for upstream interface ``LocaleFace``."""
    pass

class RenderOpts(Protocol):
    """Surface stub for upstream interface ``RenderOpts``."""
    pass

class SessionMaybeProvideInfo(Protocol):
    """Surface stub for upstream interface ``SessionMaybeProvideInfo``."""
    pass

class SessionProvideInfo(Protocol):
    """Surface stub for upstream interface ``SessionProvideInfo``."""
    pass

class SlotRenderer(Protocol):
    """Surface stub for upstream interface ``SlotRenderer``."""
    pass

class SlotRendererHost(Protocol):
    """Surface stub for upstream interface ``SlotRendererHost``."""
    pass

class StoreInstanceLike(Protocol):
    """Surface stub for upstream interface ``StoreInstanceLike``."""
    pass
