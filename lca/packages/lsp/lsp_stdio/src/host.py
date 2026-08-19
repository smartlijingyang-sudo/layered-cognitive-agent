"""Auto-generated surface skeleton for upstream ``lsp/lsp-stdio/src/host.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp-stdio/src/host.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "HostSource",
    "HostWorkspace",
    "canonicalizeWorkspace",
    "readHostSource",
]

def canonicalizeWorkspace(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``canonicalizeWorkspace``."""
    raise NotImplementedError("port canonicalizeWorkspace from lsp/lsp-stdio/src/host.ts")

def readHostSource(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readHostSource``."""
    raise NotImplementedError("port readHostSource from lsp/lsp-stdio/src/host.ts")

class HostSource(Protocol):
    """Surface stub for upstream interface ``HostSource``."""
    pass

class HostWorkspace(Protocol):
    """Surface stub for upstream interface ``HostWorkspace``."""
    pass
