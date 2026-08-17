"""Auto-generated surface skeleton for upstream ``hooks/hooks-codex/src/config.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hooks-codex/src/config.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CODEX_EVENTS",
    "CodexHookConfig",
    "ParsedCodexConfig",
    "SkippedHook",
    "parseCodexConfig",
]

CodexHookConfig: TypeAlias = object  # port: surface stub

CODEX_EVENTS = None  # port: surface stub

def parseCodexConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseCodexConfig``."""
    raise NotImplementedError("port parseCodexConfig from hooks/hooks-codex/src/config.ts")

class ParsedCodexConfig(Protocol):
    """Surface stub for upstream interface ``ParsedCodexConfig``."""
    pass

class SkippedHook(Protocol):
    """Surface stub for upstream interface ``SkippedHook``."""
    pass
