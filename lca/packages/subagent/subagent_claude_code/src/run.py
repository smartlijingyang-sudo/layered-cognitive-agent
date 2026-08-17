"""Auto-generated surface skeleton for upstream ``subagent/subagent-claude-code/src/run.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent-claude-code/src/run.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ClaudeCodeRunSpec",
    "DEFAULT_DISPOSE_GRACE_MS",
    "claudeQueryOptions",
    "consumeClaudeQuery",
    "disposeClaudeCodeChild",
    "startClaudeCodeRun",
    "successfulResult",
    "textTask",
]

DEFAULT_DISPOSE_GRACE_MS = None  # port: surface stub

def claudeQueryOptions(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``claudeQueryOptions``."""
    raise NotImplementedError("port claudeQueryOptions from subagent/subagent-claude-code/src/run.ts")

def consumeClaudeQuery(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``consumeClaudeQuery``."""
    raise NotImplementedError("port consumeClaudeQuery from subagent/subagent-claude-code/src/run.ts")

def disposeClaudeCodeChild(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``disposeClaudeCodeChild``."""
    raise NotImplementedError("port disposeClaudeCodeChild from subagent/subagent-claude-code/src/run.ts")

def startClaudeCodeRun(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``startClaudeCodeRun``."""
    raise NotImplementedError("port startClaudeCodeRun from subagent/subagent-claude-code/src/run.ts")

def successfulResult(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``successfulResult``."""
    raise NotImplementedError("port successfulResult from subagent/subagent-claude-code/src/run.ts")

def textTask(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``textTask``."""
    raise NotImplementedError("port textTask from subagent/subagent-claude-code/src/run.ts")

class ClaudeCodeRunSpec(Protocol):
    """Surface stub for upstream interface ``ClaudeCodeRunSpec``."""
    pass
