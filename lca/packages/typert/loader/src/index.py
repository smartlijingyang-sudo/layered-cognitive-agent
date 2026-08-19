"""Auto-generated surface skeleton for upstream ``typert/loader/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/loader/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "TYPERT_HOST_EXPORT",
    "Config",
    "apply",
    "inject",
    "name",
    "validateTypertManifest",
]

TYPERT_HOST_EXPORT = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from typert/loader/src/index.ts")

def validateTypertManifest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``validateTypertManifest``."""
    raise NotImplementedError("port validateTypertManifest from typert/loader/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
