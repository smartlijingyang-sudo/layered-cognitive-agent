"""Auto-generated surface skeleton for upstream ``storage/storage-domain/src/error.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-domain/src/error.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DomainError",
    "DomainErrorCode",
    "DomainErrorOptions",
    "InvalidRecordDetail",
]

DomainErrorCode: TypeAlias = object  # port: surface stub

class DomainError:
    """Surface stub for upstream class ``DomainError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DomainError.__init__ from storage/storage-domain/src/error.ts")

class DomainErrorOptions(Protocol):
    """Surface stub for upstream interface ``DomainErrorOptions``."""
    pass

class InvalidRecordDetail(Protocol):
    """Surface stub for upstream interface ``InvalidRecordDetail``."""
    pass
