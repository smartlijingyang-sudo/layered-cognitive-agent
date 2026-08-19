"""Auto-generated surface skeleton for upstream ``context/agent-instructions/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/agent-instructions/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "Config",
    "InstructionFile",
    "LoadedInstructionFile",
    "RenderedWorkspaceContext",
    "TruncatedInstruction",
    "apply",
    "discoverBaselineInstructionFiles",
    "loadBaselineInstructions",
    "name",
    "renderWorkspaceContext",
]

InstructionFile: TypeAlias = object  # port: surface stub

LoadedInstructionFile: TypeAlias = object  # port: surface stub

RenderedWorkspaceContext: TypeAlias = object  # port: surface stub

TruncatedInstruction: TypeAlias = object  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from context/agent-instructions/src/index.ts")

Config = None  # port: surface stub (reexport)

discoverBaselineInstructionFiles = None  # port: surface stub (reexport)

loadBaselineInstructions = None  # port: surface stub (reexport)

name = None  # port: surface stub (reexport)

renderWorkspaceContext = None  # port: surface stub (reexport)
