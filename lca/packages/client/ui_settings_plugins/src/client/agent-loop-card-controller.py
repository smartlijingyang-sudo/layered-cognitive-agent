"""Auto-generated surface skeleton for upstream ``client/ui-settings-plugins/src/client/agent-loop-card-controller.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-plugins/src/client/agent-loop-card-controller.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AGENT_LOOP_NS",
    "AgentLoopCardController",
    "AgentLoopCardFace",
    "AgentLoopCardState",
    "AgentLoopSettings",
]

AGENT_LOOP_NS = None  # port: surface stub

class AgentLoopCardController:
    """Surface stub for upstream class ``AgentLoopCardController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AgentLoopCardController.__init__ from client/ui-settings-plugins/src/client/agent-loop-card-controller.ts")

class AgentLoopCardFace(Protocol):
    """Surface stub for upstream interface ``AgentLoopCardFace``."""
    pass

class AgentLoopCardState(Protocol):
    """Surface stub for upstream interface ``AgentLoopCardState``."""
    pass

class AgentLoopSettings(Protocol):
    """Surface stub for upstream interface ``AgentLoopSettings``."""
    pass
