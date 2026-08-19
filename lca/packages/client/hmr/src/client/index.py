"""Auto-generated surface skeleton for upstream ``client/hmr/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/hmr/src/client/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "EVENTS_ENDPOINT",
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
    raise NotImplementedError("port apply from client/hmr/src/client/index.ts")

EVENTS_ENDPOINT = None  # port: surface stub (reexport)
