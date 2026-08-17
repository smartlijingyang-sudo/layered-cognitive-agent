"""Auto-generated surface skeleton for upstream ``context/agent-instructions/src/files.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/agent-instructions/src/files.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "InstructionFile",
    "LoadedInstructionFile",
    "ProbedInstructionFile",
    "RenderedInstructionSet",
    "ScopeInstructionProbe",
    "ancestorChain",
    "dedupInstructionFilesByDirectory",
    "descendantDirsBetween",
    "discoverBaselineInstructionFiles",
    "findProjectRoot",
    "loadBaselineInstructionSet",
    "loadBaselineInstructions",
    "probeScopeInstruction",
    "readScopeInstruction",
    "relativeDisplay",
]

ScopeInstructionProbe: TypeAlias = object  # port: surface stub

def ancestorChain(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``ancestorChain``."""
    raise NotImplementedError("port ancestorChain from context/agent-instructions/src/files.ts")

def dedupInstructionFilesByDirectory(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``dedupInstructionFilesByDirectory``."""
    raise NotImplementedError("port dedupInstructionFilesByDirectory from context/agent-instructions/src/files.ts")

def descendantDirsBetween(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``descendantDirsBetween``."""
    raise NotImplementedError("port descendantDirsBetween from context/agent-instructions/src/files.ts")

def discoverBaselineInstructionFiles(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``discoverBaselineInstructionFiles``."""
    raise NotImplementedError("port discoverBaselineInstructionFiles from context/agent-instructions/src/files.ts")

def findProjectRoot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``findProjectRoot``."""
    raise NotImplementedError("port findProjectRoot from context/agent-instructions/src/files.ts")

def loadBaselineInstructionSet(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadBaselineInstructionSet``."""
    raise NotImplementedError("port loadBaselineInstructionSet from context/agent-instructions/src/files.ts")

def loadBaselineInstructions(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadBaselineInstructions``."""
    raise NotImplementedError("port loadBaselineInstructions from context/agent-instructions/src/files.ts")

def probeScopeInstruction(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``probeScopeInstruction``."""
    raise NotImplementedError("port probeScopeInstruction from context/agent-instructions/src/files.ts")

def readScopeInstruction(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readScopeInstruction``."""
    raise NotImplementedError("port readScopeInstruction from context/agent-instructions/src/files.ts")

def relativeDisplay(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``relativeDisplay``."""
    raise NotImplementedError("port relativeDisplay from context/agent-instructions/src/files.ts")

class InstructionFile(Protocol):
    """Surface stub for upstream interface ``InstructionFile``."""
    pass

class LoadedInstructionFile(Protocol):
    """Surface stub for upstream interface ``LoadedInstructionFile``."""
    pass

class ProbedInstructionFile(Protocol):
    """Surface stub for upstream interface ``ProbedInstructionFile``."""
    pass

class RenderedInstructionSet(Protocol):
    """Surface stub for upstream interface ``RenderedInstructionSet``."""
    pass
