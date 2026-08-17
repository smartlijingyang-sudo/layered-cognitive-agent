"""Auto-generated surface skeleton for upstream ``runtime-diagnostics/invariants/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``runtime-diagnostics/invariants/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "InvariantError",
    "InvariantFailure",
    "InvariantInstaller",
    "InvariantRegistry",
]

InvariantFailure: TypeAlias = object  # port: surface stub

class InvariantError:
    """Surface stub for upstream class ``InvariantError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port InvariantError.__init__ from runtime-diagnostics/invariants/src/index.ts")

class InvariantRegistry:
    """Surface stub for upstream class ``InvariantRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port InvariantRegistry.__init__ from runtime-diagnostics/invariants/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class InvariantInstaller(Protocol):
    """Surface stub for upstream interface ``InvariantInstaller``."""
    pass
