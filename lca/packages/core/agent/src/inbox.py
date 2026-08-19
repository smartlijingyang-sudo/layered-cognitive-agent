"""Auto-generated surface skeleton for upstream ``core/agent/src/inbox.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/agent/src/inbox.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "Inbox",
    "InboxNotifications",
]

class Inbox:
    """Surface stub for upstream class ``Inbox``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port Inbox.__init__ from core/agent/src/inbox.ts")

class InboxNotifications(Protocol):
    """Surface stub for upstream interface ``InboxNotifications``."""
    pass
