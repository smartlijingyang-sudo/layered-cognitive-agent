"""Auto-generated surface skeleton for upstream ``core/agent/src/dispatch.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/agent/src/dispatch.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentEventDispatch",
    "AgentSubjectEvent",
    "agentCarrier",
    "agentEvents",
    "assembleContextFor",
    "emitAgentEvent",
]

AgentSubjectEvent: TypeAlias = object  # port: surface stub

def agentCarrier(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``agentCarrier``."""
    raise NotImplementedError("port agentCarrier from core/agent/src/dispatch.ts")

def agentEvents(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``agentEvents``."""
    raise NotImplementedError("port agentEvents from core/agent/src/dispatch.ts")

def assembleContextFor(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assembleContextFor``."""
    raise NotImplementedError("port assembleContextFor from core/agent/src/dispatch.ts")

def emitAgentEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``emitAgentEvent``."""
    raise NotImplementedError("port emitAgentEvent from core/agent/src/dispatch.ts")

class AgentEventDispatch(Protocol):
    """Surface stub for upstream interface ``AgentEventDispatch``."""
    pass
