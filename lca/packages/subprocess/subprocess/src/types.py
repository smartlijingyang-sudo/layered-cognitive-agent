"""Auto-generated surface skeleton for upstream ``subprocess/subprocess/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subprocess/subprocess/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DSH_ENV_PREFIX",
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
    "SubprocessSpawnSpec",
    "SubprocessStdinMode",
    "SubprocessStdio",
    "SubprocessTerminalForeground",
    "SubprocessTerminalHandle",
    "SubprocessTerminalSignal",
    "SubprocessTerminalSpawnSpec",
]

DshEnvironment: TypeAlias = object  # port: surface stub

DshEnvironmentKey: TypeAlias = object  # port: surface stub

SubprocessOutputMode: TypeAlias = object  # port: surface stub

SubprocessStdinMode: TypeAlias = object  # port: surface stub

SubprocessTerminalSignal: TypeAlias = object  # port: surface stub

DSH_ENV_PREFIX = None  # port: surface stub

class CollectedOutput(Protocol):
    """Surface stub for upstream interface ``CollectedOutput``."""
    pass

class SubprocessCollect(Protocol):
    """Surface stub for upstream interface ``SubprocessCollect``."""
    pass

class SubprocessCollectedOutputs(Protocol):
    """Surface stub for upstream interface ``SubprocessCollectedOutputs``."""
    pass

class SubprocessHandle(Protocol):
    """Surface stub for upstream interface ``SubprocessHandle``."""
    pass

class SubprocessOutcome(Protocol):
    """Surface stub for upstream interface ``SubprocessOutcome``."""
    pass

class SubprocessOutputRead(Protocol):
    """Surface stub for upstream interface ``SubprocessOutputRead``."""
    pass

class SubprocessOutputReader(Protocol):
    """Surface stub for upstream interface ``SubprocessOutputReader``."""
    pass

class SubprocessSpawnSpec(Protocol):
    """Surface stub for upstream interface ``SubprocessSpawnSpec``."""
    pass

class SubprocessStdio(Protocol):
    """Surface stub for upstream interface ``SubprocessStdio``."""
    pass

class SubprocessTerminalForeground(Protocol):
    """Surface stub for upstream interface ``SubprocessTerminalForeground``."""
    pass

class SubprocessTerminalHandle(Protocol):
    """Surface stub for upstream interface ``SubprocessTerminalHandle``."""
    pass

class SubprocessTerminalSpawnSpec(Protocol):
    """Surface stub for upstream interface ``SubprocessTerminalSpawnSpec``."""
    pass
