"""Auto-generated surface skeleton for upstream ``storage/storage-domain/src/domain.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-domain/src/domain.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Domain",
    "DomainGlobal",
    "DomainGlobalHandleOf",
    "DomainImpl",
    "KvTable",
]

DomainGlobalHandleOf: TypeAlias = object  # port: surface stub

class DomainImpl:
    """Surface stub for upstream class ``DomainImpl``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DomainImpl.__init__ from storage/storage-domain/src/domain.ts")

class Domain(Protocol):
    """Surface stub for upstream interface ``Domain``."""
    pass

class DomainGlobal(Protocol):
    """Surface stub for upstream interface ``DomainGlobal``."""
    pass

class KvTable(Protocol):
    """Surface stub for upstream interface ``KvTable``."""
    pass
