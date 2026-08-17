"""Auto-generated surface skeleton for upstream ``fs/fs/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/fs/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FileSystem",
    "FsDirEntry",
    "FsEditOutcome",
    "FsEditRequest",
    "FsError",
    "FsErrorCode",
    "FsInfo",
    "FsObservation",
    "FsPathInfo",
    "FsTarget",
    "FsTargetKey",
    "FsVersion",
    "FsWriteIntent",
    "FsWriteOutcome",
]

FsDirEntry: TypeAlias = object  # port: surface stub

FsEditOutcome: TypeAlias = object  # port: surface stub

FsEditRequest: TypeAlias = object  # port: surface stub

FsErrorCode: TypeAlias = object  # port: surface stub

FsInfo: TypeAlias = object  # port: surface stub

FsObservation: TypeAlias = object  # port: surface stub

FsPathInfo: TypeAlias = object  # port: surface stub

FsTarget: TypeAlias = object  # port: surface stub

FsWriteIntent: TypeAlias = object  # port: surface stub

FsWriteOutcome: TypeAlias = object  # port: surface stub

class FileSystem:
    """Surface stub for upstream class ``FileSystem``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FileSystem.__init__ from fs/fs/src/index.ts")

FsError = None  # port: surface stub (reexport)

FsTargetKey = None  # port: surface stub (reexport)

FsVersion = None  # port: surface stub (reexport)
