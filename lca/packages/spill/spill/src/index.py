"""Auto-generated surface skeleton for upstream ``spill/spill/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``spill/spill/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "SaveTextSpill",
    "SpillLocator",
    "SpillOwner",
    "SpillRef",
    "SpillSource",
    "SpillStore",
]

SaveTextSpill: TypeAlias = object  # port: surface stub

SpillOwner: TypeAlias = object  # port: surface stub

SpillRef: TypeAlias = object  # port: surface stub

SpillSource: TypeAlias = object  # port: surface stub

class SpillStore:
    """Surface stub for upstream class ``SpillStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SpillStore.__init__ from spill/spill/src/index.ts")

SpillLocator = None  # port: surface stub (reexport)
