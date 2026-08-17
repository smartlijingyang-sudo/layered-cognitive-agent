"""Auto-generated surface skeleton for upstream ``code-runtime/code-runtime-worker-thread/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``code-runtime/code-runtime-worker-thread/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "WorkerThreadCodeRuntime",
]

class WorkerThreadCodeRuntime:
    """Surface stub for upstream class ``WorkerThreadCodeRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkerThreadCodeRuntime.__init__ from code-runtime/code-runtime-worker-thread/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
