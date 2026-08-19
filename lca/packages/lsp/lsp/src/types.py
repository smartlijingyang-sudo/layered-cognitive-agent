"""Auto-generated surface skeleton for upstream ``lsp/lsp/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "LspHover",
    "LspLocation",
    "LspOperation",
    "LspPosition",
    "LspProvider",
    "LspProviderQuery",
    "LspQueryRequest",
    "LspQueryResult",
    "LspRange",
    "LspService",
]

LspOperation: TypeAlias = object  # port: surface stub

LspQueryResult: TypeAlias = object  # port: surface stub

class LspHover(Protocol):
    """Surface stub for upstream interface ``LspHover``."""
    pass

class LspLocation(Protocol):
    """Surface stub for upstream interface ``LspLocation``."""
    pass

class LspPosition(Protocol):
    """Surface stub for upstream interface ``LspPosition``."""
    pass

class LspProvider(Protocol):
    """Surface stub for upstream interface ``LspProvider``."""
    pass

class LspProviderQuery(Protocol):
    """Surface stub for upstream interface ``LspProviderQuery``."""
    pass

class LspQueryRequest(Protocol):
    """Surface stub for upstream interface ``LspQueryRequest``."""
    pass

class LspRange(Protocol):
    """Surface stub for upstream interface ``LspRange``."""
    pass

class LspService(Protocol):
    """Surface stub for upstream interface ``LspService``."""
    pass
