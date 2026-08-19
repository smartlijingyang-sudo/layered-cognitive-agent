"""Auto-generated surface skeleton for upstream ``core/agent/src/runtime-types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/agent/src/runtime-types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Agent",
    "AgentCancelCause",
    "AgentOptions",
    "AgentStatus",
    "CancelOptions",
    "PreStepDecision",
    "RequestErrorAction",
    "SessionStartSource",
]

AgentCancelCause: TypeAlias = object  # port: surface stub

AgentStatus: TypeAlias = object  # port: surface stub

PreStepDecision: TypeAlias = object  # port: surface stub

RequestErrorAction: TypeAlias = object  # port: surface stub

SessionStartSource: TypeAlias = object  # port: surface stub

class Agent(Protocol):
    """Surface stub for upstream interface ``Agent``."""
    pass

class AgentOptions(Protocol):
    """Surface stub for upstream interface ``AgentOptions``."""
    pass

class CancelOptions(Protocol):
    """Surface stub for upstream interface ``CancelOptions``."""
    pass
