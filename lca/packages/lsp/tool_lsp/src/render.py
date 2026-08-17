"""Auto-generated surface skeleton for upstream ``lsp/tool-lsp/src/render.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/tool-lsp/src/render.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_MAX_LOCATIONS",
    "DEFAULT_MAX_RESULT_CHARS",
    "LSP_OPERATIONS",
    "LspToolArgs",
    "LspToolInput",
    "formatHover",
    "formatLocations",
    "parseLspArgs",
    "presentLspCall",
    "renderUri",
]

DEFAULT_MAX_LOCATIONS = None  # port: surface stub

DEFAULT_MAX_RESULT_CHARS = None  # port: surface stub

LSP_OPERATIONS = None  # port: surface stub

def formatHover(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatHover``."""
    raise NotImplementedError("port formatHover from lsp/tool-lsp/src/render.ts")

def formatLocations(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatLocations``."""
    raise NotImplementedError("port formatLocations from lsp/tool-lsp/src/render.ts")

def parseLspArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseLspArgs``."""
    raise NotImplementedError("port parseLspArgs from lsp/tool-lsp/src/render.ts")

def presentLspCall(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``presentLspCall``."""
    raise NotImplementedError("port presentLspCall from lsp/tool-lsp/src/render.ts")

def renderUri(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderUri``."""
    raise NotImplementedError("port renderUri from lsp/tool-lsp/src/render.ts")

class LspToolArgs(Protocol):
    """Surface stub for upstream interface ``LspToolArgs``."""
    pass

class LspToolInput(Protocol):
    """Surface stub for upstream interface ``LspToolInput``."""
    pass
