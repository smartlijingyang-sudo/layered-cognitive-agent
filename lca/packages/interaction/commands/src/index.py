"""Auto-generated surface skeleton for upstream ``interaction/commands/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``interaction/commands/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "CommandDefinition",
    "CommandId",
    "CommandInvocation",
    "CommandRuntime",
    "ParsedCommand",
    "name",
    "parseCommand",
]

name = None  # port: surface stub

def parseCommand(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseCommand``."""
    raise NotImplementedError("port parseCommand from interaction/commands/src/index.ts")

class CommandRuntime:
    """Surface stub for upstream class ``CommandRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CommandRuntime.__init__ from interaction/commands/src/index.ts")

CommandId = None  # port: surface stub (reexport)

class CommandDefinition(Protocol):
    """Surface stub for upstream interface ``CommandDefinition``."""
    pass

class CommandInvocation(Protocol):
    """Surface stub for upstream interface ``CommandInvocation``."""
    pass

class ParsedCommand(Protocol):
    """Surface stub for upstream interface ``ParsedCommand``."""
    pass
