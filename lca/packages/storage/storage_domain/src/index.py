"""Auto-generated surface skeleton for upstream ``storage/storage-domain/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-domain/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "Domain",
    "DomainChanged",
    "DomainError",
    "DomainErrorCode",
    "DomainErrorOptions",
    "DomainFacility",
    "DomainGlobal",
    "DomainGlobalHandleOf",
    "DomainGlobalSpec",
    "DomainSpec",
    "DomainTableSpec",
    "GlobalValueOf",
    "InvalidRecordDetail",
    "KvTable",
    "TableKeyOf",
    "TableValueOf",
    "apply",
    "defineDomain",
    "descriptorOf",
    "domainTable",
    "inject",
    "name",
]

Domain: TypeAlias = object  # port: surface stub

DomainChanged: TypeAlias = object  # port: surface stub

DomainErrorCode: TypeAlias = object  # port: surface stub

DomainErrorOptions: TypeAlias = object  # port: surface stub

DomainGlobal: TypeAlias = object  # port: surface stub

DomainGlobalHandleOf: TypeAlias = object  # port: surface stub

DomainGlobalSpec: TypeAlias = object  # port: surface stub

DomainSpec: TypeAlias = object  # port: surface stub

DomainTableSpec: TypeAlias = object  # port: surface stub

GlobalValueOf: TypeAlias = object  # port: surface stub

InvalidRecordDetail: TypeAlias = object  # port: surface stub

KvTable: TypeAlias = object  # port: surface stub

TableKeyOf: TypeAlias = object  # port: surface stub

TableValueOf: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from storage/storage-domain/src/index.ts")

class DomainFacility:
    """Surface stub for upstream class ``DomainFacility``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DomainFacility.__init__ from storage/storage-domain/src/index.ts")

DomainError = None  # port: surface stub (reexport)

defineDomain = None  # port: surface stub (reexport)

descriptorOf = None  # port: surface stub (reexport)

domainTable = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
