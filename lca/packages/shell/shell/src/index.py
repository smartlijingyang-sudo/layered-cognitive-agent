"""Auto-generated surface skeleton for upstream ``shell/shell/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``shell/shell/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "DSH_ENV_PREFIX",
    "SHELL_SETTINGS_NAMESPACE",
    "CollectedOutput",
    "DshEnvironment",
    "DshEnvironmentKey",
    "ParsedExitStatus",
    "ShellExecRequest",
    "ShellExecSpec",
    "ShellExecutor",
    "ShellProcess",
    "ShellProcessRead",
    "ShellProcessStatus",
    "ShellRunResult",
    "ShellSandboxInfo",
    "parseExitStatus",
]

CollectedOutput: TypeAlias = object  # port: surface stub

DshEnvironment: TypeAlias = object  # port: surface stub

DshEnvironmentKey: TypeAlias = object  # port: surface stub

ParsedExitStatus: TypeAlias = object  # port: surface stub

ShellExecRequest: TypeAlias = object  # port: surface stub

ShellExecSpec: TypeAlias = object  # port: surface stub

ShellProcess: TypeAlias = object  # port: surface stub

ShellProcessRead: TypeAlias = object  # port: surface stub

ShellProcessStatus: TypeAlias = object  # port: surface stub

ShellRunResult: TypeAlias = object  # port: surface stub

ShellSandboxInfo: TypeAlias = object  # port: surface stub

SHELL_SETTINGS_NAMESPACE = None  # port: surface stub

class ShellExecutor:
    """Surface stub for upstream class ``ShellExecutor``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ShellExecutor.__init__ from shell/shell/src/index.ts")

DSH_ENV_PREFIX = None  # port: surface stub (reexport)

parseExitStatus = None  # port: surface stub (reexport)
