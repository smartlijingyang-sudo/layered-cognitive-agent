"""Auto-generated surface skeleton for upstream ``storage/storage-domain/src/spec.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-domain/src/spec.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DomainGlobalSpec",
    "DomainSpec",
    "DomainTableSpec",
    "GlobalValueOf",
    "TableKeyOf",
    "TableValueOf",
    "defineDomain",
    "descriptorOf",
    "domainTable",
]

GlobalValueOf: TypeAlias = object  # port: surface stub

TableKeyOf: TypeAlias = object  # port: surface stub

TableValueOf: TypeAlias = object  # port: surface stub

def defineDomain(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``defineDomain``."""
    raise NotImplementedError("port defineDomain from storage/storage-domain/src/spec.ts")

def descriptorOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``descriptorOf``."""
    raise NotImplementedError("port descriptorOf from storage/storage-domain/src/spec.ts")

def domainTable(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``domainTable``."""
    raise NotImplementedError("port domainTable from storage/storage-domain/src/spec.ts")

class DomainGlobalSpec(Protocol):
    """Surface stub for upstream interface ``DomainGlobalSpec``."""
    pass

class DomainSpec(Protocol):
    """Surface stub for upstream interface ``DomainSpec``."""
    pass

class DomainTableSpec(Protocol):
    """Surface stub for upstream interface ``DomainTableSpec``."""
    pass
