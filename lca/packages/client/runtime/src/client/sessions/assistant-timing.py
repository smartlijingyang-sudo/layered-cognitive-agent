"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/assistant-timing.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/assistant-timing.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "AssistantStepMetadata",
    "assistantStepKey",
    "indexAssistantStepTiming",
    "isTokenDelta",
    "settledAssistantTiming",
]

def assistantStepKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assistantStepKey``."""
    raise NotImplementedError("port assistantStepKey from client/runtime/src/client/sessions/assistant-timing.ts")

def indexAssistantStepTiming(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``indexAssistantStepTiming``."""
    raise NotImplementedError("port indexAssistantStepTiming from client/runtime/src/client/sessions/assistant-timing.ts")

def settledAssistantTiming(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``settledAssistantTiming``."""
    raise NotImplementedError("port settledAssistantTiming from client/runtime/src/client/sessions/assistant-timing.ts")

isTokenDelta = None  # port: surface stub (reexport)

class AssistantStepMetadata(Protocol):
    """Surface stub for upstream interface ``AssistantStepMetadata``."""
    pass
