"""Auto-generated surface skeleton for upstream ``lsp/lsp-stdio/src/connection.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp-stdio/src/connection.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ConnectionSpawner",
    "ConnectionSpec",
    "ConnectionWriter",
    "LspConnection",
]

ConnectionSpawner: TypeAlias = object  # port: surface stub

ConnectionWriter: TypeAlias = object  # port: surface stub

class LspConnection:
    """Surface stub for upstream class ``LspConnection``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LspConnection.__init__ from lsp/lsp-stdio/src/connection.ts")

class ConnectionSpec(Protocol):
    """Surface stub for upstream interface ``ConnectionSpec``."""
    pass
