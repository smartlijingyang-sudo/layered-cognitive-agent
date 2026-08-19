"""Auto-generated surface skeleton for upstream ``context/session-reference/src/uri.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/session-reference/src/uri.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SESSION_REFERENCE_SCHEME",
    "ParsedSessionReferenceText",
    "decodeSessionReferenceUri",
    "encodeSessionReferenceUri",
    "formatSessionReferenceMention",
    "parseSessionReferenceText",
]

SESSION_REFERENCE_SCHEME = None  # port: surface stub

def decodeSessionReferenceUri(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeSessionReferenceUri``."""
    raise NotImplementedError("port decodeSessionReferenceUri from context/session-reference/src/uri.ts")

def encodeSessionReferenceUri(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``encodeSessionReferenceUri``."""
    raise NotImplementedError("port encodeSessionReferenceUri from context/session-reference/src/uri.ts")

def formatSessionReferenceMention(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatSessionReferenceMention``."""
    raise NotImplementedError("port formatSessionReferenceMention from context/session-reference/src/uri.ts")

def parseSessionReferenceText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseSessionReferenceText``."""
    raise NotImplementedError("port parseSessionReferenceText from context/session-reference/src/uri.ts")

class ParsedSessionReferenceText(Protocol):
    """Surface stub for upstream interface ``ParsedSessionReferenceText``."""
    pass
