"""Auto-generated surface skeleton for upstream ``core/scope/src/store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/scope/src/store.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AnonymousEntries",
    "NamedEntries",
    "ScopeLayer",
    "ScopedLayers",
]

class AnonymousEntries:
    """Surface stub for upstream class ``AnonymousEntries``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AnonymousEntries.__init__ from core/scope/src/store.ts")

class NamedEntries:
    """Surface stub for upstream class ``NamedEntries``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port NamedEntries.__init__ from core/scope/src/store.ts")

class ScopedLayers:
    """Surface stub for upstream class ``ScopedLayers``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ScopedLayers.__init__ from core/scope/src/store.ts")

class ScopeLayer(Protocol):
    """Surface stub for upstream interface ``ScopeLayer``."""
    pass
