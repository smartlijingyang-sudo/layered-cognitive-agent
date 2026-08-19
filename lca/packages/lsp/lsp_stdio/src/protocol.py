"""Auto-generated surface skeleton for upstream ``lsp/lsp-stdio/src/protocol.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp-stdio/src/protocol.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WireHover",
    "WireInitializeResult",
    "WireLocation",
    "WireLocationLink",
    "WireMarkedString",
    "WireMarkedStringObject",
    "WireMarkupContent",
    "WirePosition",
    "WireProviderCapability",
    "WireRange",
    "WireServerCapabilities",
    "WireTextDocumentSyncKind",
    "WireTextDocumentSyncOptions",
]

WireMarkedString: TypeAlias = object  # port: surface stub

WireProviderCapability: TypeAlias = object  # port: surface stub

WireTextDocumentSyncKind: TypeAlias = object  # port: surface stub

class WireHover(Protocol):
    """Surface stub for upstream interface ``WireHover``."""
    pass

class WireInitializeResult(Protocol):
    """Surface stub for upstream interface ``WireInitializeResult``."""
    pass

class WireLocation(Protocol):
    """Surface stub for upstream interface ``WireLocation``."""
    pass

class WireLocationLink(Protocol):
    """Surface stub for upstream interface ``WireLocationLink``."""
    pass

class WireMarkedStringObject(Protocol):
    """Surface stub for upstream interface ``WireMarkedStringObject``."""
    pass

class WireMarkupContent(Protocol):
    """Surface stub for upstream interface ``WireMarkupContent``."""
    pass

class WirePosition(Protocol):
    """Surface stub for upstream interface ``WirePosition``."""
    pass

class WireRange(Protocol):
    """Surface stub for upstream interface ``WireRange``."""
    pass

class WireServerCapabilities(Protocol):
    """Surface stub for upstream interface ``WireServerCapabilities``."""
    pass

class WireTextDocumentSyncOptions(Protocol):
    """Surface stub for upstream interface ``WireTextDocumentSyncOptions``."""
    pass
