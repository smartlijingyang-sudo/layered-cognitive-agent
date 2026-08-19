"""Auto-generated surface skeleton for upstream ``session/session-title/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-title/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "SessionTitleAutomaticMode",
    "SessionTitleEventData",
    "SessionTitleInvalidError",
    "SessionTitleModelProvenance",
    "SessionTitleProvider",
    "SessionTitleProviderId",
    "SessionTitleProviderRequest",
    "SessionTitleProviderResult",
    "SessionTitleService",
    "SessionTitleSnapshot",
    "SessionTitleSource",
    "SessionTitleUserMessage",
    "collectSessionTitleMessages",
    "fallbackSessionTitle",
    "foldSessionTitle",
    "normalizeSessionTitle",
    "truncateTitleUtf8",
]

SessionTitleAutomaticMode: TypeAlias = object  # port: surface stub

SessionTitleProviderId: TypeAlias = object  # port: surface stub

SessionTitleSource: TypeAlias = object  # port: surface stub

def collectSessionTitleMessages(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``collectSessionTitleMessages``."""
    raise NotImplementedError("port collectSessionTitleMessages from session/session-title/src/index.ts")

def foldSessionTitle(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``foldSessionTitle``."""
    raise NotImplementedError("port foldSessionTitle from session/session-title/src/index.ts")

class SessionTitleInvalidError:
    """Surface stub for upstream class ``SessionTitleInvalidError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionTitleInvalidError.__init__ from session/session-title/src/index.ts")

class SessionTitleService:
    """Surface stub for upstream class ``SessionTitleService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionTitleService.__init__ from session/session-title/src/index.ts")

fallbackSessionTitle = None  # port: surface stub (reexport)

normalizeSessionTitle = None  # port: surface stub (reexport)

truncateTitleUtf8 = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class SessionTitleEventData(Protocol):
    """Surface stub for upstream interface ``SessionTitleEventData``."""
    pass

class SessionTitleModelProvenance(Protocol):
    """Surface stub for upstream interface ``SessionTitleModelProvenance``."""
    pass

class SessionTitleProvider(Protocol):
    """Surface stub for upstream interface ``SessionTitleProvider``."""
    pass

class SessionTitleProviderRequest(Protocol):
    """Surface stub for upstream interface ``SessionTitleProviderRequest``."""
    pass

class SessionTitleProviderResult(Protocol):
    """Surface stub for upstream interface ``SessionTitleProviderResult``."""
    pass

class SessionTitleSnapshot(Protocol):
    """Surface stub for upstream interface ``SessionTitleSnapshot``."""
    pass

class SessionTitleUserMessage(Protocol):
    """Surface stub for upstream interface ``SessionTitleUserMessage``."""
    pass
