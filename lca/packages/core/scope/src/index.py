"""Auto-generated surface skeleton for upstream ``core/scope/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/scope/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AnonymousEntries",
    "CreateScopeOptions",
    "NamedEntries",
    "Scope",
    "ScopeKey",
    "ScopeLayer",
    "ScopeParentBinding",
    "Scoped",
    "ScopedLayers",
    "bindScopeParent",
    "carrierKeyOf",
    "createScope",
    "isScopeCarrier",
    "scopeChainOf",
    "scopeOf",
    "scopeParentOf",
    "scopeTarget",
]

ScopeKey: TypeAlias = object  # port: surface stub

ScopeLayer: TypeAlias = object  # port: surface stub

Scoped: TypeAlias = object  # port: surface stub

def bindScopeParent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``bindScopeParent``."""
    raise NotImplementedError("port bindScopeParent from core/scope/src/index.ts")

def carrierKeyOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``carrierKeyOf``."""
    raise NotImplementedError("port carrierKeyOf from core/scope/src/index.ts")

def createScope(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createScope``."""
    raise NotImplementedError("port createScope from core/scope/src/index.ts")

def isScopeCarrier(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isScopeCarrier``."""
    raise NotImplementedError("port isScopeCarrier from core/scope/src/index.ts")

def scopeChainOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scopeChainOf``."""
    raise NotImplementedError("port scopeChainOf from core/scope/src/index.ts")

def scopeOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scopeOf``."""
    raise NotImplementedError("port scopeOf from core/scope/src/index.ts")

def scopeParentOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scopeParentOf``."""
    raise NotImplementedError("port scopeParentOf from core/scope/src/index.ts")

def scopeTarget(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scopeTarget``."""
    raise NotImplementedError("port scopeTarget from core/scope/src/index.ts")

AnonymousEntries = None  # port: surface stub (reexport)

NamedEntries = None  # port: surface stub (reexport)

ScopedLayers = None  # port: surface stub (reexport)

class CreateScopeOptions(Protocol):
    """Surface stub for upstream interface ``CreateScopeOptions``."""
    pass

class Scope(Protocol):
    """Surface stub for upstream interface ``Scope``."""
    pass

class ScopeParentBinding(Protocol):
    """Surface stub for upstream interface ``ScopeParentBinding``."""
    pass
