"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api/events.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api/events.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "EventsApi",
    "HostFrame",
    "MuxFrame",
    "QueuedInboxItem",
    "ToolCallView",
    "ToolEventView",
    "ToolResultView",
]

HostFrame: TypeAlias = object  # port: surface stub

MuxFrame: TypeAlias = object  # port: surface stub

ToolCallView: TypeAlias = object  # port: surface stub

ToolEventView: TypeAlias = object  # port: surface stub

ToolResultView: TypeAlias = object  # port: surface stub

class EventsApi(Protocol):
    """Surface stub for upstream interface ``EventsApi``."""
    pass

class QueuedInboxItem(Protocol):
    """Surface stub for upstream interface ``QueuedInboxItem``."""
    pass
