"""Auto-generated surface skeleton for upstream ``fs/fs-sandbox/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/fs-sandbox/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "SandboxedFileSystem",
]

Config: TypeAlias = object  # port: surface stub

class SandboxedFileSystem:
    """Surface stub for upstream class ``SandboxedFileSystem``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SandboxedFileSystem.__init__ from fs/fs-sandbox/src/index.ts")
