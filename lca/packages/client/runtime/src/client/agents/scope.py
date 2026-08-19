"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/agents/scope.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/agents/scope.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentContext",
    "AgentScopeHandle",
    "createScope",
    "scopeOf",
]

AgentContext: TypeAlias = object  # port: surface stub

def createScope(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createScope``."""
    raise NotImplementedError("port createScope from client/runtime/src/client/agents/scope.ts")

def scopeOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scopeOf``."""
    raise NotImplementedError("port scopeOf from client/runtime/src/client/agents/scope.ts")

class AgentScopeHandle(Protocol):
    """Surface stub for upstream interface ``AgentScopeHandle``."""
    pass
