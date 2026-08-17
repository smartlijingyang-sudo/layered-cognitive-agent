"""Auto-generated surface skeleton for upstream ``hooks/hook-protocol/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hook-protocol/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CommandHook",
    "HookDialect",
    "HookOutput",
    "MatcherGroup",
    "MatcherMode",
]

HookDialect: TypeAlias = object  # port: surface stub

MatcherMode: TypeAlias = object  # port: surface stub

class CommandHook(Protocol):
    """Surface stub for upstream interface ``CommandHook``."""
    pass

class HookOutput(Protocol):
    """Surface stub for upstream interface ``HookOutput``."""
    pass

class MatcherGroup(Protocol):
    """Surface stub for upstream interface ``MatcherGroup``."""
    pass
