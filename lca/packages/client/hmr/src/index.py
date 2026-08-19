"""Auto-generated surface skeleton for upstream ``client/hmr/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/hmr/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "EVENTS_ENDPOINT",
    "Config",
    "PluginsEventFrame",
    "apply",
    "inject",
    "name",
]

PluginsEventFrame: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/hmr/src/index.ts")

EVENTS_ENDPOINT = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
