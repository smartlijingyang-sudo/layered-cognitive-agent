"""Auto-generated surface skeleton for upstream ``e2b/subprocess-e2b/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``e2b/subprocess-e2b/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "E2BSubprocessRuntime",
]

class E2BSubprocessRuntime:
    """Surface stub for upstream class ``E2BSubprocessRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port E2BSubprocessRuntime.__init__ from e2b/subprocess-e2b/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
