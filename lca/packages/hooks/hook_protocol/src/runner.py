"""Auto-generated surface skeleton for upstream ``hooks/hook-protocol/src/runner.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hook-protocol/src/runner.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_HOOK_TIMEOUT_MS",
    "RunHookOptions",
    "RunHookResult",
    "runHook",
]

DEFAULT_HOOK_TIMEOUT_MS = None  # port: surface stub

def runHook(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``runHook``."""
    raise NotImplementedError("port runHook from hooks/hook-protocol/src/runner.ts")

class RunHookOptions(Protocol):
    """Surface stub for upstream interface ``RunHookOptions``."""
    pass

class RunHookResult(Protocol):
    """Surface stub for upstream interface ``RunHookResult``."""
    pass
