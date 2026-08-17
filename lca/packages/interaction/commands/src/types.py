"""Auto-generated surface skeleton for upstream ``interaction/commands/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``interaction/commands/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CommandDescriptor",
    "CommandExecution",
    "CommandInputDescriptor",
    "CommandResult",
    "CommandSource",
    "CommandSourceMap",
]

CommandResult: TypeAlias = object  # port: surface stub

CommandSource: TypeAlias = object  # port: surface stub

class CommandDescriptor(Protocol):
    """Surface stub for upstream interface ``CommandDescriptor``."""
    pass

class CommandExecution(Protocol):
    """Surface stub for upstream interface ``CommandExecution``."""
    pass

class CommandInputDescriptor(Protocol):
    """Surface stub for upstream interface ``CommandInputDescriptor``."""
    pass

class CommandSourceMap(Protocol):
    """Surface stub for upstream interface ``CommandSourceMap``."""
    pass
