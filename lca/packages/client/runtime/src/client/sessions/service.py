"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/service.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/service.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SessionBinding",
    "SessionCreateError",
    "SessionForkError",
    "SessionListState",
    "SessionProvideContribution",
    "SessionProvideDescriptor",
    "SessionRuntime",
    "SessionSummary",
    "scopeOf",
    "workspaceTitleOf",
]

def workspaceTitleOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``workspaceTitleOf``."""
    raise NotImplementedError("port workspaceTitleOf from client/runtime/src/client/sessions/service.ts")

class SessionCreateError:
    """Surface stub for upstream class ``SessionCreateError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionCreateError.__init__ from client/runtime/src/client/sessions/service.ts")

class SessionForkError:
    """Surface stub for upstream class ``SessionForkError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionForkError.__init__ from client/runtime/src/client/sessions/service.ts")

class SessionRuntime:
    """Surface stub for upstream class ``SessionRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionRuntime.__init__ from client/runtime/src/client/sessions/service.ts")

scopeOf = None  # port: surface stub (reexport)

class SessionBinding(Protocol):
    """Surface stub for upstream interface ``SessionBinding``."""
    pass

class SessionListState(Protocol):
    """Surface stub for upstream interface ``SessionListState``."""
    pass

class SessionProvideContribution(Protocol):
    """Surface stub for upstream interface ``SessionProvideContribution``."""
    pass

class SessionProvideDescriptor(Protocol):
    """Surface stub for upstream interface ``SessionProvideDescriptor``."""
    pass

class SessionSummary(Protocol):
    """Surface stub for upstream interface ``SessionSummary``."""
    pass
