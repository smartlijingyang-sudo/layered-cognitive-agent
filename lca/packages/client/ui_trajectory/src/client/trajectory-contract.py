"""Auto-generated surface skeleton for upstream ``client/ui-trajectory/src/client/trajectory-contract.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-trajectory/src/client/trajectory-contract.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "TrajectoryContribution",
    "TrajectoryConversationViewNode",
    "TrajectoryRequestHeaderState",
    "TrajectorySnapshot",
]

TrajectoryContribution: TypeAlias = object  # port: surface stub

class TrajectoryConversationViewNode(Protocol):
    """Surface stub for upstream interface ``TrajectoryConversationViewNode``."""
    pass

class TrajectoryRequestHeaderState(Protocol):
    """Surface stub for upstream interface ``TrajectoryRequestHeaderState``."""
    pass

class TrajectorySnapshot(Protocol):
    """Surface stub for upstream interface ``TrajectorySnapshot``."""
    pass
