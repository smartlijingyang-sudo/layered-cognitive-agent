"""Auto-generated surface skeleton for upstream ``subprocess/subprocess-local/src/spawn.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subprocess/subprocess-local/src/spawn.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "LocalSubprocessHandle",
    "OutputCollector",
    "SpawnInternals",
    "childEnv",
    "killGroup",
    "spawnSubprocess",
    "taskkillProcessTree",
]

def childEnv(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``childEnv``."""
    raise NotImplementedError("port childEnv from subprocess/subprocess-local/src/spawn.ts")

def killGroup(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``killGroup``."""
    raise NotImplementedError("port killGroup from subprocess/subprocess-local/src/spawn.ts")

def spawnSubprocess(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``spawnSubprocess``."""
    raise NotImplementedError("port spawnSubprocess from subprocess/subprocess-local/src/spawn.ts")

def taskkillProcessTree(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``taskkillProcessTree``."""
    raise NotImplementedError("port taskkillProcessTree from subprocess/subprocess-local/src/spawn.ts")

class OutputCollector:
    """Surface stub for upstream class ``OutputCollector``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port OutputCollector.__init__ from subprocess/subprocess-local/src/spawn.ts")

class LocalSubprocessHandle(Protocol):
    """Surface stub for upstream interface ``LocalSubprocessHandle``."""
    pass

class SpawnInternals(Protocol):
    """Surface stub for upstream interface ``SpawnInternals``."""
    pass
