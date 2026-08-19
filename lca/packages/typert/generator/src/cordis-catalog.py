"""Auto-generated surface skeleton for upstream ``typert/generator/src/cordis-catalog.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/generator/src/cordis-catalog.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "REGION_BEGIN",
    "REGION_END",
    "CordisCatalogModel",
    "CordisCatalogPolicy",
    "CordisCatalogProjector",
    "EventEntry",
    "InheritedEntry",
    "ServiceEntry",
    "ServiceMethodEntry",
    "collectEvents",
    "collectServices",
    "projectCordisCatalog",
    "renderInheritedPage",
    "renderPageRegion",
]

REGION_BEGIN = None  # port: surface stub

REGION_END = None  # port: surface stub

def collectEvents(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``collectEvents``."""
    raise NotImplementedError("port collectEvents from typert/generator/src/cordis-catalog.ts")

def collectServices(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``collectServices``."""
    raise NotImplementedError("port collectServices from typert/generator/src/cordis-catalog.ts")

def projectCordisCatalog(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``projectCordisCatalog``."""
    raise NotImplementedError("port projectCordisCatalog from typert/generator/src/cordis-catalog.ts")

def renderInheritedPage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderInheritedPage``."""
    raise NotImplementedError("port renderInheritedPage from typert/generator/src/cordis-catalog.ts")

def renderPageRegion(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderPageRegion``."""
    raise NotImplementedError("port renderPageRegion from typert/generator/src/cordis-catalog.ts")

class CordisCatalogProjector:
    """Surface stub for upstream class ``CordisCatalogProjector``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CordisCatalogProjector.__init__ from typert/generator/src/cordis-catalog.ts")

class CordisCatalogModel(Protocol):
    """Surface stub for upstream interface ``CordisCatalogModel``."""
    pass

class CordisCatalogPolicy(Protocol):
    """Surface stub for upstream interface ``CordisCatalogPolicy``."""
    pass

class EventEntry(Protocol):
    """Surface stub for upstream interface ``EventEntry``."""
    pass

class InheritedEntry(Protocol):
    """Surface stub for upstream interface ``InheritedEntry``."""
    pass

class ServiceEntry(Protocol):
    """Surface stub for upstream interface ``ServiceEntry``."""
    pass

class ServiceMethodEntry(Protocol):
    """Surface stub for upstream interface ``ServiceMethodEntry``."""
    pass
