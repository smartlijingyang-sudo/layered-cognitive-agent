"""Auto-generated surface skeleton for upstream ``context/session-reference/src/config.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/session-reference/src/config.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "DEFAULT_CANDIDATE_LIMIT",
    "DEFAULT_MAX_REFERENCE_BYTES",
    "MAX_REFERENCES",
    "SessionReferenceError",
    "SessionReferenceErrorCode",
]

SessionReferenceErrorCode: TypeAlias = object  # port: surface stub

DEFAULT_CANDIDATE_LIMIT = None  # port: surface stub

DEFAULT_MAX_REFERENCE_BYTES = None  # port: surface stub

MAX_REFERENCES = None  # port: surface stub

class SessionReferenceError:
    """Surface stub for upstream class ``SessionReferenceError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionReferenceError.__init__ from context/session-reference/src/config.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
