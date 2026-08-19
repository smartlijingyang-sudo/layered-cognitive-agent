"""Auto-generated surface skeleton for upstream ``hooks/hooks-claude-code/src/config.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hooks-claude-code/src/config.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ClaudeCodeHookConfig",
    "ParsedClaudeConfig",
    "SkippedHook",
    "SubstitutionVars",
    "parseClaudeCodeConfig",
    "substituteCommand",
]

ClaudeCodeHookConfig: TypeAlias = object  # port: surface stub

def parseClaudeCodeConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseClaudeCodeConfig``."""
    raise NotImplementedError("port parseClaudeCodeConfig from hooks/hooks-claude-code/src/config.ts")

def substituteCommand(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``substituteCommand``."""
    raise NotImplementedError("port substituteCommand from hooks/hooks-claude-code/src/config.ts")

class ParsedClaudeConfig(Protocol):
    """Surface stub for upstream interface ``ParsedClaudeConfig``."""
    pass

class SkippedHook(Protocol):
    """Surface stub for upstream interface ``SkippedHook``."""
    pass

class SubstitutionVars(Protocol):
    """Surface stub for upstream interface ``SubstitutionVars``."""
    pass
