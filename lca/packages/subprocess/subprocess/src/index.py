"""Auto-generated surface skeleton for upstream ``subprocess/subprocess/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subprocess/subprocess/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "DSH_ENV_PREFIX",
    "SENSITIVE_ENV_PATTERN",
    "CollectedOutput",
    "DshEnvironment",
    "DshEnvironmentKey",
    "SubprocessCollect",
    "SubprocessCollectedOutputs",
    "SubprocessHandle",
    "SubprocessOutcome",
    "SubprocessOutputMode",
    "SubprocessOutputRead",
    "SubprocessOutputReader",
    "SubprocessRuntime",
    "SubprocessSpawnSpec",
    "SubprocessStdinMode",
    "SubprocessStdio",
    "SubprocessTerminalForeground",
    "SubprocessTerminalHandle",
    "SubprocessTerminalSignal",
    "SubprocessTerminalSpawnSpec",
    "scrubbedParentEnv",
]

CollectedOutput: TypeAlias = object  # port: surface stub

DshEnvironment: TypeAlias = object  # port: surface stub

DshEnvironmentKey: TypeAlias = object  # port: surface stub

SubprocessCollect: TypeAlias = object  # port: surface stub

SubprocessCollectedOutputs: TypeAlias = object  # port: surface stub

SubprocessHandle: TypeAlias = object  # port: surface stub

SubprocessOutcome: TypeAlias = object  # port: surface stub

SubprocessOutputMode: TypeAlias = object  # port: surface stub

SubprocessOutputRead: TypeAlias = object  # port: surface stub

SubprocessOutputReader: TypeAlias = object  # port: surface stub

SubprocessSpawnSpec: TypeAlias = object  # port: surface stub

SubprocessStdinMode: TypeAlias = object  # port: surface stub

SubprocessStdio: TypeAlias = object  # port: surface stub

SubprocessTerminalForeground: TypeAlias = object  # port: surface stub

SubprocessTerminalHandle: TypeAlias = object  # port: surface stub

SubprocessTerminalSignal: TypeAlias = object  # port: surface stub

SubprocessTerminalSpawnSpec: TypeAlias = object  # port: surface stub

SENSITIVE_ENV_PATTERN = None  # port: surface stub

def scrubbedParentEnv(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scrubbedParentEnv``."""
    raise NotImplementedError("port scrubbedParentEnv from subprocess/subprocess/src/index.ts")

class SubprocessRuntime:
    """Surface stub for upstream class ``SubprocessRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SubprocessRuntime.__init__ from subprocess/subprocess/src/index.ts")

DSH_ENV_PREFIX = None  # port: surface stub (reexport)
