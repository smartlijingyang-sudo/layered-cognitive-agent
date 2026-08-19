"""Auto-generated surface skeleton for upstream ``subagent/subagent-codex/src/run.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent-codex/src/run.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DEFAULT_DISPOSE_GRACE_MS",
    "CodexRunSpec",
    "codexAppServerArgv",
    "disposeCodexChild",
    "startCodexRun",
    "textTask",
]

DEFAULT_DISPOSE_GRACE_MS = None  # port: surface stub

def codexAppServerArgv(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``codexAppServerArgv``."""
    raise NotImplementedError("port codexAppServerArgv from subagent/subagent-codex/src/run.ts")

def disposeCodexChild(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``disposeCodexChild``."""
    raise NotImplementedError("port disposeCodexChild from subagent/subagent-codex/src/run.ts")

def startCodexRun(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``startCodexRun``."""
    raise NotImplementedError("port startCodexRun from subagent/subagent-codex/src/run.ts")

def textTask(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``textTask``."""
    raise NotImplementedError("port textTask from subagent/subagent-codex/src/run.ts")

class CodexRunSpec(Protocol):
    """Surface stub for upstream interface ``CodexRunSpec``."""
    pass
