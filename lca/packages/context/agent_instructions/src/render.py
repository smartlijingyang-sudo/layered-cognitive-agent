"""Auto-generated surface skeleton for upstream ``context/agent-instructions/src/render.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/agent-instructions/src/render.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "USER_GLOBAL_DIRECTORY",
    "USER_GLOBAL_FILE",
    "AgentInstructionChange",
    "ChangeRenderItem",
    "RenderedWorkspaceContext",
    "TruncatedInstruction",
    "candidateScopeKey",
    "decodeScopeKey",
    "instructionScopeKey",
    "renderInstructionChanges",
    "renderWorkspaceContext",
    "renderWorkspaceInstructionSet",
    "scopeForDisplayPath",
]

USER_GLOBAL_DIRECTORY = None  # port: surface stub

USER_GLOBAL_FILE = None  # port: surface stub

def candidateScopeKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``candidateScopeKey``."""
    raise NotImplementedError("port candidateScopeKey from context/agent-instructions/src/render.ts")

def decodeScopeKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeScopeKey``."""
    raise NotImplementedError("port decodeScopeKey from context/agent-instructions/src/render.ts")

def instructionScopeKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``instructionScopeKey``."""
    raise NotImplementedError("port instructionScopeKey from context/agent-instructions/src/render.ts")

def renderInstructionChanges(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderInstructionChanges``."""
    raise NotImplementedError("port renderInstructionChanges from context/agent-instructions/src/render.ts")

def renderWorkspaceContext(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderWorkspaceContext``."""
    raise NotImplementedError("port renderWorkspaceContext from context/agent-instructions/src/render.ts")

def renderWorkspaceInstructionSet(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderWorkspaceInstructionSet``."""
    raise NotImplementedError("port renderWorkspaceInstructionSet from context/agent-instructions/src/render.ts")

def scopeForDisplayPath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scopeForDisplayPath``."""
    raise NotImplementedError("port scopeForDisplayPath from context/agent-instructions/src/render.ts")

class AgentInstructionChange(Protocol):
    """Surface stub for upstream interface ``AgentInstructionChange``."""
    pass

class ChangeRenderItem(Protocol):
    """Surface stub for upstream interface ``ChangeRenderItem``."""
    pass

class RenderedWorkspaceContext(Protocol):
    """Surface stub for upstream interface ``RenderedWorkspaceContext``."""
    pass

class TruncatedInstruction(Protocol):
    """Surface stub for upstream interface ``TruncatedInstruction``."""
    pass
