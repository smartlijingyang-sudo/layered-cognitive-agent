"""Auto-generated surface skeleton for upstream ``preset/persona/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``preset/persona/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "PERSONA_ORDER",
    "PERSONA_SECTION",
    "Config",
    "apply",
    "inject",
    "name",
]

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from preset/persona/src/index.ts")

PERSONA_ORDER = None  # port: surface stub (reexport)

PERSONA_SECTION = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
