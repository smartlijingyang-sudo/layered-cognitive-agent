"""Auto-generated surface skeleton for upstream ``hooks/hook-protocol/src/events.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hook-protocol/src/events.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DEFAULT_STDERR_SUMMARY_MAX_CHARS",
    "HookInvocation",
    "HookResultRecord",
    "appendHookInvoked",
    "appendHookResult",
    "summarizeStderr",
]

DEFAULT_STDERR_SUMMARY_MAX_CHARS = None  # port: surface stub

def appendHookInvoked(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``appendHookInvoked``."""
    raise NotImplementedError("port appendHookInvoked from hooks/hook-protocol/src/events.ts")

def appendHookResult(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``appendHookResult``."""
    raise NotImplementedError("port appendHookResult from hooks/hook-protocol/src/events.ts")

def summarizeStderr(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``summarizeStderr``."""
    raise NotImplementedError("port summarizeStderr from hooks/hook-protocol/src/events.ts")

class HookInvocation(Protocol):
    """Surface stub for upstream interface ``HookInvocation``."""
    pass

class HookResultRecord(Protocol):
    """Surface stub for upstream interface ``HookResultRecord``."""
    pass
