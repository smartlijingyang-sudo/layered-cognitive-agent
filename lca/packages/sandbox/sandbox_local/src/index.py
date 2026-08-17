"""Auto-generated surface skeleton for upstream ``sandbox/sandbox-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox-local/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "LocalSandboxProvider",
    "SandboxInternals",
]

class LocalSandboxProvider:
    """Surface stub for upstream class ``LocalSandboxProvider``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocalSandboxProvider.__init__ from sandbox/sandbox-local/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class SandboxInternals(Protocol):
    """Surface stub for upstream interface ``SandboxInternals``."""
    pass
