"""Auto-generated surface skeleton for upstream ``fs/fs-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/fs-local/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "Config",
    "LocalFileSystem",
]

class LocalFileSystem:
    """Surface stub for upstream class ``LocalFileSystem``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocalFileSystem.__init__ from fs/fs-local/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
