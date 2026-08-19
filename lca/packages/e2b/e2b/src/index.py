"""Auto-generated surface skeleton for upstream ``e2b/e2b/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``e2b/e2b/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CommandExitError",
    "CommandHandle",
    "CommandResult",
    "Config",
    "E2BRuntime",
    "EntryInfo",
    "FileNotFoundError",
    "FileType",
    "Sandbox",
    "SandboxNotFoundError",
    "e2bControlEnvs",
    "quoteE2BShellArg",
]

CommandHandle: TypeAlias = object  # port: surface stub

CommandResult: TypeAlias = object  # port: surface stub

EntryInfo: TypeAlias = object  # port: surface stub

def e2bControlEnvs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``e2bControlEnvs``."""
    raise NotImplementedError("port e2bControlEnvs from e2b/e2b/src/index.ts")

def quoteE2BShellArg(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``quoteE2BShellArg``."""
    raise NotImplementedError("port quoteE2BShellArg from e2b/e2b/src/index.ts")

class E2BRuntime:
    """Surface stub for upstream class ``E2BRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port E2BRuntime.__init__ from e2b/e2b/src/index.ts")

CommandExitError = None  # port: surface stub (reexport)

FileNotFoundError = None  # port: surface stub (reexport)

FileType = None  # port: surface stub (reexport)

Sandbox = None  # port: surface stub (reexport)

SandboxNotFoundError = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
