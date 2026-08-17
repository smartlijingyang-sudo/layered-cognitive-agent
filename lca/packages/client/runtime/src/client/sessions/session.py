"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/session.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/session.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PAGE_MESSAGES",
    "Session",
    "SessionOptions",
]

PAGE_MESSAGES = None  # port: surface stub

class Session:
    """Surface stub for upstream class ``Session``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port Session.__init__ from client/runtime/src/client/sessions/session.ts")

class SessionOptions(Protocol):
    """Surface stub for upstream interface ``SessionOptions``."""
    pass
