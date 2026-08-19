"""Auto-generated surface skeleton for upstream ``skill/tool-skill/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``skill/tool-skill/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "Config",
    "SkillCatalogSource",
    "apply",
    "inject",
    "name",
]

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from skill/tool-skill/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class SkillCatalogSource(Protocol):
    """Surface stub for upstream interface ``SkillCatalogSource``."""
    pass
