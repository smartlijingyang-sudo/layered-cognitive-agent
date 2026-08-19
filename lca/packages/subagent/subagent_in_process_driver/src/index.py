"""Auto-generated surface skeleton for upstream ``subagent/subagent-in-process-driver/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent-in-process-driver/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "STRUCTURED_OUTPUT_INSTRUCTION",
    "STRUCTURED_OUTPUT_TOOL",
    "InProcessRunOptions",
    "startInProcessRun",
]

def startInProcessRun(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``startInProcessRun``."""
    raise NotImplementedError("port startInProcessRun from subagent/subagent-in-process-driver/src/index.ts")

STRUCTURED_OUTPUT_INSTRUCTION = None  # port: surface stub (reexport)

STRUCTURED_OUTPUT_TOOL = None  # port: surface stub (reexport)

class InProcessRunOptions(Protocol):
    """Surface stub for upstream interface ``InProcessRunOptions``."""
    pass
