"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/out-of-process.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/out-of-process.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "NO_START_CAPABILITIES",
    "RunResultSettlement",
    "SubprocessRunHandleParts",
    "assertPositiveFinite",
    "assertUsableCwd",
    "resolveChildCwd",
    "settleRunResult",
    "subprocessRunHandle",
    "validateConfiguredCwd",
]

NO_START_CAPABILITIES = None  # port: surface stub

def assertPositiveFinite(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertPositiveFinite``."""
    raise NotImplementedError("port assertPositiveFinite from subagent/subagent/src/out-of-process.ts")

def assertUsableCwd(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertUsableCwd``."""
    raise NotImplementedError("port assertUsableCwd from subagent/subagent/src/out-of-process.ts")

def resolveChildCwd(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveChildCwd``."""
    raise NotImplementedError("port resolveChildCwd from subagent/subagent/src/out-of-process.ts")

def settleRunResult(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``settleRunResult``."""
    raise NotImplementedError("port settleRunResult from subagent/subagent/src/out-of-process.ts")

def subprocessRunHandle(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``subprocessRunHandle``."""
    raise NotImplementedError("port subprocessRunHandle from subagent/subagent/src/out-of-process.ts")

def validateConfiguredCwd(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``validateConfiguredCwd``."""
    raise NotImplementedError("port validateConfiguredCwd from subagent/subagent/src/out-of-process.ts")

class RunResultSettlement(Protocol):
    """Surface stub for upstream interface ``RunResultSettlement``."""
    pass

class SubprocessRunHandleParts(Protocol):
    """Surface stub for upstream interface ``SubprocessRunHandleParts``."""
    pass
