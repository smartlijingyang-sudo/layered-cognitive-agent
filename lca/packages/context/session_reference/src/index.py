"""Auto-generated surface skeleton for upstream ``context/session-reference/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/session-reference/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "DEFAULT_CANDIDATE_LIMIT",
    "DEFAULT_MAX_REFERENCE_BYTES",
    "MAX_REFERENCES",
    "SESSION_REFERENCE_SCHEME",
    "SessionReferenceError",
    "SessionReferenceErrorCode",
    "SessionReferenceResolver",
    "decodeSessionReferenceUri",
    "encodeSessionReferenceUri",
    "formatSessionReferenceMention",
    "parseSessionReferenceText",
]

Config: TypeAlias = object  # port: surface stub

SessionReferenceErrorCode: TypeAlias = object  # port: surface stub

class SessionReferenceResolver:
    """Surface stub for upstream class ``SessionReferenceResolver``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionReferenceResolver.__init__ from context/session-reference/src/index.ts")

DEFAULT_CANDIDATE_LIMIT = None  # port: surface stub (reexport)

DEFAULT_MAX_REFERENCE_BYTES = None  # port: surface stub (reexport)

MAX_REFERENCES = None  # port: surface stub (reexport)

SESSION_REFERENCE_SCHEME = None  # port: surface stub (reexport)

SessionReferenceError = None  # port: surface stub (reexport)

decodeSessionReferenceUri = None  # port: surface stub (reexport)

encodeSessionReferenceUri = None  # port: surface stub (reexport)

formatSessionReferenceMention = None  # port: surface stub (reexport)

parseSessionReferenceText = None  # port: surface stub (reexport)
