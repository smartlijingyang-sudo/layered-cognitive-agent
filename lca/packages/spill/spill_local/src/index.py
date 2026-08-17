"""Auto-generated surface skeleton for upstream ``spill/spill-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``spill/spill-local/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "LocalSpillStore",
    "SaveTextOptions",
    "SavedText",
    "encodeSegment",
    "privateRoot",
    "saveTextFile",
    "sessionDir",
]

SaveTextOptions: TypeAlias = object  # port: surface stub

SavedText: TypeAlias = object  # port: surface stub

class LocalSpillStore:
    """Surface stub for upstream class ``LocalSpillStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocalSpillStore.__init__ from spill/spill-local/src/index.ts")

encodeSegment = None  # port: surface stub (reexport)

privateRoot = None  # port: surface stub (reexport)

saveTextFile = None  # port: surface stub (reexport)

sessionDir = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
