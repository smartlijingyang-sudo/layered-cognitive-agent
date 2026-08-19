"""Auto-generated surface skeleton for upstream ``client/ui-model-selection/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-model-selection/src/client/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "ModelDirectory",
    "ModelDirectoryResolver",
    "ModelDirectoryState",
    "ModelKey",
    "ModelSelectInjected",
    "apply",
    "inject",
]

ModelDirectoryState: TypeAlias = object  # port: surface stub

ModelKey: TypeAlias = object  # port: surface stub

ModelSelectInjected: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/ui-model-selection/src/client/index.ts")

ModelDirectory = None  # port: surface stub (reexport)

ModelDirectoryResolver = None  # port: surface stub (reexport)
