"""Auto-generated surface skeleton for upstream ``lsp/lsp/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Lsp",
    "LspError",
    "LspHover",
    "LspLocation",
    "LspOperation",
    "LspPosition",
    "LspProvider",
    "LspProviderId",
    "LspProviderQuery",
    "LspQueryRequest",
    "LspQueryResult",
    "LspRange",
    "LspService",
    "finalExtension",
]

LspHover: TypeAlias = object  # port: surface stub

LspLocation: TypeAlias = object  # port: surface stub

LspOperation: TypeAlias = object  # port: surface stub

LspPosition: TypeAlias = object  # port: surface stub

LspProvider: TypeAlias = object  # port: surface stub

LspProviderQuery: TypeAlias = object  # port: surface stub

LspQueryRequest: TypeAlias = object  # port: surface stub

LspQueryResult: TypeAlias = object  # port: surface stub

LspRange: TypeAlias = object  # port: surface stub

LspService: TypeAlias = object  # port: surface stub

def finalExtension(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``finalExtension``."""
    raise NotImplementedError("port finalExtension from lsp/lsp/src/index.ts")

class Lsp:
    """Surface stub for upstream class ``Lsp``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port Lsp.__init__ from lsp/lsp/src/index.ts")

class LspError:
    """Surface stub for upstream class ``LspError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LspError.__init__ from lsp/lsp/src/index.ts")

LspProviderId = None  # port: surface stub (reexport)
