"""Auto-generated surface skeleton for upstream ``core/agent/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/agent/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentEventDispatch",
    "AgentFactory",
    "AgentHandle",
    "AgentRegistry",
    "AgentSetup",
    "AgentSetupCommit",
    "AgentSubjectEvent",
    "CreateAgentOptions",
    "ResumeAgentOptions",
    "agentCarrier",
    "agentEvents",
    "assembleContextFor",
    "emitAgentEvent",
]

AgentEventDispatch: TypeAlias = object  # port: surface stub

AgentSetup: TypeAlias = object  # port: surface stub

AgentSubjectEvent: TypeAlias = object  # port: surface stub

class AgentRegistry:
    """Surface stub for upstream class ``AgentRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AgentRegistry.__init__ from core/agent/src/index.ts")

agentCarrier = None  # port: surface stub (reexport)

agentEvents = None  # port: surface stub (reexport)

assembleContextFor = None  # port: surface stub (reexport)

emitAgentEvent = None  # port: surface stub (reexport)

class AgentFactory(Protocol):
    """Surface stub for upstream interface ``AgentFactory``."""
    pass

class AgentHandle(Protocol):
    """Surface stub for upstream interface ``AgentHandle``."""
    pass

class AgentSetupCommit(Protocol):
    """Surface stub for upstream interface ``AgentSetupCommit``."""
    pass

class CreateAgentOptions(Protocol):
    """Surface stub for upstream interface ``CreateAgentOptions``."""
    pass

class ResumeAgentOptions(Protocol):
    """Surface stub for upstream interface ``ResumeAgentOptions``."""
    pass
