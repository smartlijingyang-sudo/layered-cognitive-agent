"""Auto-generated surface skeleton for upstream ``test-support/client-runtime/src/fixtures.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/client-runtime/src/fixtures.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SessionBehaviorOverrides",
    "SessionFixture",
    "Stabilizer",
    "conversationSnapshot",
    "workspaceListState",
]

SessionBehaviorOverrides: TypeAlias = object  # port: surface stub

Stabilizer: TypeAlias = object  # port: surface stub

def conversationSnapshot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``conversationSnapshot``."""
    raise NotImplementedError("port conversationSnapshot from test-support/client-runtime/src/fixtures.ts")

def workspaceListState(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``workspaceListState``."""
    raise NotImplementedError("port workspaceListState from test-support/client-runtime/src/fixtures.ts")

class SessionFixture(Protocol):
    """Surface stub for upstream interface ``SessionFixture``."""
    pass
