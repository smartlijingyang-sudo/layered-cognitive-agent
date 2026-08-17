"""Auto-generated surface skeleton for upstream ``subagent/subagent-in-process-driver/src/structured.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent-in-process-driver/src/structured.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "STRUCTURED_OUTPUT_INSTRUCTION",
    "STRUCTURED_OUTPUT_TOOL",
    "StructuredAttachment",
    "attachStructuredRuntime",
]

STRUCTURED_OUTPUT_INSTRUCTION = None  # port: surface stub

STRUCTURED_OUTPUT_TOOL = None  # port: surface stub

def attachStructuredRuntime(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``attachStructuredRuntime``."""
    raise NotImplementedError("port attachStructuredRuntime from subagent/subagent-in-process-driver/src/structured.ts")

class StructuredAttachment(Protocol):
    """Surface stub for upstream interface ``StructuredAttachment``."""
    pass
