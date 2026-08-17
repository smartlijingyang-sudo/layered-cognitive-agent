"""Auto-generated surface skeleton for upstream ``util/timeout/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``util/timeout/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Deadline",
    "IdleWatchdog",
    "MAX_TIMER_DELAY_MS",
    "TimeoutReason",
    "clampTimeout",
    "deadline",
    "idleWatchdog",
    "timeoutOf",
]

MAX_TIMER_DELAY_MS = None  # port: surface stub

def clampTimeout(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``clampTimeout``."""
    raise NotImplementedError("port clampTimeout from util/timeout/src/index.ts")

def deadline(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deadline``."""
    raise NotImplementedError("port deadline from util/timeout/src/index.ts")

def idleWatchdog(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``idleWatchdog``."""
    raise NotImplementedError("port idleWatchdog from util/timeout/src/index.ts")

def timeoutOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``timeoutOf``."""
    raise NotImplementedError("port timeoutOf from util/timeout/src/index.ts")

class TimeoutReason:
    """Surface stub for upstream class ``TimeoutReason``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TimeoutReason.__init__ from util/timeout/src/index.ts")

class Deadline(Protocol):
    """Surface stub for upstream interface ``Deadline``."""
    pass

class IdleWatchdog(Protocol):
    """Surface stub for upstream interface ``IdleWatchdog``."""
    pass
