"""Auto-generated surface skeleton for upstream ``skill/skill-filesystem/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``skill/skill-filesystem/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "Config",
    "FileSystemSkillProvider",
    "apply",
    "inject",
    "name",
]

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from skill/skill-filesystem/src/index.ts")

class FileSystemSkillProvider:
    """Surface stub for upstream class ``FileSystemSkillProvider``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FileSystemSkillProvider.__init__ from skill/skill-filesystem/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
