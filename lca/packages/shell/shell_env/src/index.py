"""Auto-generated surface skeleton for upstream ``shell/shell-env/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``shell/shell-env/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "BashEnvContributor",
    "BashEnvVariable",
    "BashEnvVariableInfo",
    "Config",
    "ShellEnvRegistry",
    "apply",
    "inject",
    "name",
]

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from shell/shell-env/src/index.ts")

class ShellEnvRegistry:
    """Surface stub for upstream class ``ShellEnvRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ShellEnvRegistry.__init__ from shell/shell-env/src/index.ts")

class BashEnvContributor(Protocol):
    """Surface stub for upstream interface ``BashEnvContributor``."""
    pass

class BashEnvVariable(Protocol):
    """Surface stub for upstream interface ``BashEnvVariable``."""
    pass

class BashEnvVariableInfo(Protocol):
    """Surface stub for upstream interface ``BashEnvVariableInfo``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
