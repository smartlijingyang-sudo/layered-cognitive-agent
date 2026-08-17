"""Auto-generated surface skeleton for upstream ``client/ui-settings-models/src/client/welcome-store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-models/src/client/welcome-store.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WelcomeNoticeState",
    "WelcomeNoticeStore",
    "refreshWelcomeIfLoaded",
]

def refreshWelcomeIfLoaded(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``refreshWelcomeIfLoaded``."""
    raise NotImplementedError("port refreshWelcomeIfLoaded from client/ui-settings-models/src/client/welcome-store.ts")

class WelcomeNoticeStore:
    """Surface stub for upstream class ``WelcomeNoticeStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WelcomeNoticeStore.__init__ from client/ui-settings-models/src/client/welcome-store.ts")

class WelcomeNoticeState(Protocol):
    """Surface stub for upstream interface ``WelcomeNoticeState``."""
    pass
