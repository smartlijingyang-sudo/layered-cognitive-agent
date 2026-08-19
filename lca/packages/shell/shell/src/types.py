"""Auto-generated surface skeleton for upstream ``shell/shell/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``shell/shell/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DSH_ENV_PREFIX",
    "CollectedOutput",
    "DshEnvironment",
    "DshEnvironmentKey",
    "ShellExecRequest",
    "ShellExecSpec",
    "ShellProcess",
    "ShellProcessRead",
    "ShellProcessStatus",
    "ShellRunResult",
    "ShellSandboxInfo",
]

CollectedOutput: TypeAlias = object  # port: surface stub

DshEnvironment: TypeAlias = object  # port: surface stub

DshEnvironmentKey: TypeAlias = object  # port: surface stub

ShellProcessStatus: TypeAlias = object  # port: surface stub

DSH_ENV_PREFIX = None  # port: surface stub (reexport)

class ShellExecRequest(Protocol):
    """Surface stub for upstream interface ``ShellExecRequest``."""
    pass

class ShellExecSpec(Protocol):
    """Surface stub for upstream interface ``ShellExecSpec``."""
    pass

class ShellProcess(Protocol):
    """Surface stub for upstream interface ``ShellProcess``."""
    pass

class ShellProcessRead(Protocol):
    """Surface stub for upstream interface ``ShellProcessRead``."""
    pass

class ShellRunResult(Protocol):
    """Surface stub for upstream interface ``ShellRunResult``."""
    pass

class ShellSandboxInfo(Protocol):
    """Surface stub for upstream interface ``ShellSandboxInfo``."""
    pass
