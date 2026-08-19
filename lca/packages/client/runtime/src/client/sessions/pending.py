"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/pending.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/pending.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PendingInteraction",
    "PendingInteractionStatus",
    "PendingKind",
    "PendingPayloads",
    "PendingWait",
]

PendingInteraction: TypeAlias = object  # port: surface stub

PendingInteractionStatus: TypeAlias = object  # port: surface stub

PendingKind: TypeAlias = object  # port: surface stub

class PendingWait:
    """Surface stub for upstream class ``PendingWait``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PendingWait.__init__ from client/runtime/src/client/sessions/pending.ts")

class PendingPayloads(Protocol):
    """Surface stub for upstream interface ``PendingPayloads``."""
    pass
