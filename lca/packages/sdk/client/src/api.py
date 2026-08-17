"""Auto-generated surface skeleton for upstream ``sdk/client/src/api.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/client/src/api.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DeepSeekHarness",
    "HarnessSession",
    "RunOptions",
    "finalResponse",
    "normalizeInput",
]

def finalResponse(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``finalResponse``."""
    raise NotImplementedError("port finalResponse from sdk/client/src/api.ts")

def normalizeInput(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``normalizeInput``."""
    raise NotImplementedError("port normalizeInput from sdk/client/src/api.ts")

class DeepSeekHarness:
    """Surface stub for upstream class ``DeepSeekHarness``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DeepSeekHarness.__init__ from sdk/client/src/api.ts")

class HarnessSession:
    """Surface stub for upstream class ``HarnessSession``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port HarnessSession.__init__ from sdk/client/src/api.ts")

class RunOptions(Protocol):
    """Surface stub for upstream interface ``RunOptions``."""
    pass
