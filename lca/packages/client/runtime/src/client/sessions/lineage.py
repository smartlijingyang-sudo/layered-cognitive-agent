"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/lineage.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/lineage.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SessionListEntry",
    "TitledSessionSummary",
    "flattenLineage",
]

def flattenLineage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``flattenLineage``."""
    raise NotImplementedError("port flattenLineage from client/runtime/src/client/sessions/lineage.ts")

class SessionListEntry(Protocol):
    """Surface stub for upstream interface ``SessionListEntry``."""
    pass

class TitledSessionSummary(Protocol):
    """Surface stub for upstream interface ``TitledSessionSummary``."""
    pass
