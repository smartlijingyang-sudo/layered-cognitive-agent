"""Auto-generated surface skeleton for upstream ``llm/llm-pi-ai/src/replay.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-pi-ai/src/replay.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PiAiReplayState",
    "toPiAssistant",
    "toPiReplayState",
]

def toPiAssistant(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toPiAssistant``."""
    raise NotImplementedError("port toPiAssistant from llm/llm-pi-ai/src/replay.ts")

def toPiReplayState(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toPiReplayState``."""
    raise NotImplementedError("port toPiReplayState from llm/llm-pi-ai/src/replay.ts")

class PiAiReplayState(Protocol):
    """Surface stub for upstream interface ``PiAiReplayState``."""
    pass
