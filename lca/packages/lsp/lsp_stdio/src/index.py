"""Auto-generated surface skeleton for upstream ``lsp/lsp-stdio/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp-stdio/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "Config",
    "LspConnection",
    "LspInstance",
    "LspLocalServerConfig",
    "MessageDecoder",
    "apply",
    "canonicalizeWorkspace",
    "encodeMessage",
    "inject",
    "name",
    "negotiatePositionEncoding",
    "normalizeHover",
    "normalizeLocations",
    "readHostSource",
    "requestMethod",
    "supportsOperation",
    "supportsTransientOpen",
]

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from lsp/lsp-stdio/src/index.ts")

LspConnection = None  # port: surface stub (reexport)

LspInstance = None  # port: surface stub (reexport)

MessageDecoder = None  # port: surface stub (reexport)

canonicalizeWorkspace = None  # port: surface stub (reexport)

encodeMessage = None  # port: surface stub (reexport)

negotiatePositionEncoding = None  # port: surface stub (reexport)

normalizeHover = None  # port: surface stub (reexport)

normalizeLocations = None  # port: surface stub (reexport)

readHostSource = None  # port: surface stub (reexport)

requestMethod = None  # port: surface stub (reexport)

supportsOperation = None  # port: surface stub (reexport)

supportsTransientOpen = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class LspLocalServerConfig(Protocol):
    """Surface stub for upstream interface ``LspLocalServerConfig``."""
    pass
