"""Auto-generated surface skeleton for upstream ``boot/cmdline/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``boot/cmdline/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AppExit",
    "CmdlineArgs",
    "CmdlineHost",
    "internals",
    "parseCmdline",
    "provideCmdline",
]

internals = None  # port: surface stub

def parseCmdline(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseCmdline``."""
    raise NotImplementedError("port parseCmdline from boot/cmdline/src/index.ts")

def provideCmdline(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``provideCmdline``."""
    raise NotImplementedError("port provideCmdline from boot/cmdline/src/index.ts")

class AppExit(Protocol):
    """Surface stub for upstream interface ``AppExit``."""
    pass

class CmdlineArgs(Protocol):
    """Surface stub for upstream interface ``CmdlineArgs``."""
    pass

class CmdlineHost(Protocol):
    """Surface stub for upstream interface ``CmdlineHost``."""
    pass
