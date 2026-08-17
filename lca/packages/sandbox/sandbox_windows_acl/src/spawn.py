"""Auto-generated surface skeleton for upstream ``sandbox/sandbox-windows-acl/src/spawn.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox-windows-acl/src/spawn.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SpawnedInherited",
    "SpawnedNative",
    "buildCommandLine",
    "drainPipe",
    "quoteArg",
    "spawnSandboxed",
    "spawnSandboxedInherited",
    "waitForExit",
]

def buildCommandLine(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``buildCommandLine``."""
    raise NotImplementedError("port buildCommandLine from sandbox/sandbox-windows-acl/src/spawn.ts")

def drainPipe(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``drainPipe``."""
    raise NotImplementedError("port drainPipe from sandbox/sandbox-windows-acl/src/spawn.ts")

def quoteArg(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``quoteArg``."""
    raise NotImplementedError("port quoteArg from sandbox/sandbox-windows-acl/src/spawn.ts")

def spawnSandboxed(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``spawnSandboxed``."""
    raise NotImplementedError("port spawnSandboxed from sandbox/sandbox-windows-acl/src/spawn.ts")

def spawnSandboxedInherited(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``spawnSandboxedInherited``."""
    raise NotImplementedError("port spawnSandboxedInherited from sandbox/sandbox-windows-acl/src/spawn.ts")

def waitForExit(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``waitForExit``."""
    raise NotImplementedError("port waitForExit from sandbox/sandbox-windows-acl/src/spawn.ts")

class SpawnedInherited(Protocol):
    """Surface stub for upstream interface ``SpawnedInherited``."""
    pass

class SpawnedNative(Protocol):
    """Surface stub for upstream interface ``SpawnedNative``."""
    pass
