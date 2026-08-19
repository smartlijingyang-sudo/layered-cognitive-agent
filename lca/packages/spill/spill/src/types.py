"""Auto-generated surface skeleton for upstream ``spill/spill/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``spill/spill/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SaveTextSpill",
    "SpillLocator",
    "SpillOwner",
    "SpillRef",
    "SpillSource",
]

SpillLocator: TypeAlias = object  # port: surface stub

class SaveTextSpill(Protocol):
    """Surface stub for upstream interface ``SaveTextSpill``."""
    pass

class SpillOwner(Protocol):
    """Surface stub for upstream interface ``SpillOwner``."""
    pass

class SpillRef(Protocol):
    """Surface stub for upstream interface ``SpillRef``."""
    pass

class SpillSource(Protocol):
    """Surface stub for upstream interface ``SpillSource``."""
    pass
