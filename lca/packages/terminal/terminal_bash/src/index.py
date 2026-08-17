"""Auto-generated surface skeleton for upstream ``terminal/terminal-bash/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``terminal/terminal-bash/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "BashTerminalBackend",
    "Config",
    "TerminalLocalConfig",
    "apply",
    "inject",
    "name",
]

TerminalLocalConfig: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from terminal/terminal-bash/src/index.ts")

class BashTerminalBackend:
    """Surface stub for upstream class ``BashTerminalBackend``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port BashTerminalBackend.__init__ from terminal/terminal-bash/src/index.ts")

Config = None  # port: surface stub (reexport)
