"""Auto-generated surface skeleton for upstream ``session-query/session-query/src/config.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/session-query/src/config.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SESSION_QUERY_DEFAULT_PERSISTED_INSPECT_CONCURRENCY",
    "SESSION_QUERY_READ_WINDOW_MAX",
    "Config",
    "SessionQueryError",
    "SessionQueryErrorCode",
]

SessionQueryErrorCode: TypeAlias = object  # port: surface stub

SESSION_QUERY_DEFAULT_PERSISTED_INSPECT_CONCURRENCY = None  # port: surface stub

SESSION_QUERY_READ_WINDOW_MAX = None  # port: surface stub

class SessionQueryError:
    """Surface stub for upstream class ``SessionQueryError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionQueryError.__init__ from session-query/session-query/src/config.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
