"""Auto-generated surface skeleton for upstream ``context/agent-instructions/src/state.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/agent-instructions/src/state.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentInstructionSource",
    "InstructionVersionCache",
    "InstructionVersionState",
    "InstructionVersionUpdate",
    "ReconciledInstructionContext",
    "applyInstructionVersionUpdates",
    "baselineInstructionState",
    "name",
    "reconcileInstructionContext",
    "retainedInstructionVersionUpdates",
    "workspaceContextMessage",
]

InstructionVersionCache: TypeAlias = object  # port: surface stub

name = None  # port: surface stub

def applyInstructionVersionUpdates(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyInstructionVersionUpdates``."""
    raise NotImplementedError("port applyInstructionVersionUpdates from context/agent-instructions/src/state.ts")

def baselineInstructionState(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``baselineInstructionState``."""
    raise NotImplementedError("port baselineInstructionState from context/agent-instructions/src/state.ts")

def reconcileInstructionContext(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``reconcileInstructionContext``."""
    raise NotImplementedError("port reconcileInstructionContext from context/agent-instructions/src/state.ts")

def retainedInstructionVersionUpdates(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``retainedInstructionVersionUpdates``."""
    raise NotImplementedError("port retainedInstructionVersionUpdates from context/agent-instructions/src/state.ts")

def workspaceContextMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``workspaceContextMessage``."""
    raise NotImplementedError("port workspaceContextMessage from context/agent-instructions/src/state.ts")

class AgentInstructionSource(Protocol):
    """Surface stub for upstream interface ``AgentInstructionSource``."""
    pass

class InstructionVersionState(Protocol):
    """Surface stub for upstream interface ``InstructionVersionState``."""
    pass

class InstructionVersionUpdate(Protocol):
    """Surface stub for upstream interface ``InstructionVersionUpdate``."""
    pass

class ReconciledInstructionContext(Protocol):
    """Surface stub for upstream interface ``ReconciledInstructionContext``."""
    pass
