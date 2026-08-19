"""Auto-generated surface skeleton for upstream ``hooks/hook-protocol/src/merge.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hook-protocol/src/merge.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "MergedDecision",
    "MergedHookOutcome",
    "mergeHookOutputs",
]

MergedDecision: TypeAlias = object  # port: surface stub

def mergeHookOutputs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``mergeHookOutputs``."""
    raise NotImplementedError("port mergeHookOutputs from hooks/hook-protocol/src/merge.ts")

class MergedHookOutcome(Protocol):
    """Surface stub for upstream interface ``MergedHookOutcome``."""
    pass
