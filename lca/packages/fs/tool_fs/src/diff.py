"""Auto-generated surface skeleton for upstream ``fs/tool-fs/src/diff.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs/src/diff.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DIFF_CONTEXT",
    "FsDiffMeta",
    "computeHunkDiffs",
    "diffsFromMeta",
]

FsDiffMeta: TypeAlias = object  # port: surface stub

DIFF_CONTEXT = None  # port: surface stub

def computeHunkDiffs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``computeHunkDiffs``."""
    raise NotImplementedError("port computeHunkDiffs from fs/tool-fs/src/diff.ts")

def diffsFromMeta(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``diffsFromMeta``."""
    raise NotImplementedError("port diffsFromMeta from fs/tool-fs/src/diff.ts")
