"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/chat/turn-metrics.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/chat/turn-metrics.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "StepReading",
    "TurnMetrics",
    "assistantStepReading",
    "deriveTurnMetrics",
]

def assistantStepReading(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assistantStepReading``."""
    raise NotImplementedError("port assistantStepReading from client/ui-conversation/src/client/chat/turn-metrics.ts")

def deriveTurnMetrics(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveTurnMetrics``."""
    raise NotImplementedError("port deriveTurnMetrics from client/ui-conversation/src/client/chat/turn-metrics.ts")

class StepReading(Protocol):
    """Surface stub for upstream interface ``StepReading``."""
    pass

class TurnMetrics(Protocol):
    """Surface stub for upstream interface ``TurnMetrics``."""
    pass
