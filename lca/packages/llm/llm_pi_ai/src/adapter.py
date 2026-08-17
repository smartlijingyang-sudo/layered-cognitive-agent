"""Auto-generated surface skeleton for upstream ``llm/llm-pi-ai/src/adapter.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-pi-ai/src/adapter.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PiAiAdapter",
    "PiAiAdapterOptions",
]

class PiAiAdapter:
    """Surface stub for upstream class ``PiAiAdapter``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PiAiAdapter.__init__ from llm/llm-pi-ai/src/adapter.ts")

class PiAiAdapterOptions(Protocol):
    """Surface stub for upstream interface ``PiAiAdapterOptions``."""
    pass
