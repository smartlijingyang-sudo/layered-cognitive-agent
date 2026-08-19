"""Auto-generated surface skeleton for upstream ``host/directory-picker-native/src/win32-dialog-logic.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker-native/src/win32-dialog-logic.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "FOS_FORCEFILESYSTEM",
    "FOS_NOCHANGEDIR",
    "FOS_PICKFOLDERS",
    "HRESULT_CANCELLED",
    "Win32DialogBindings",
    "Win32FolderDialog",
    "runFolderDialog",
]

FOS_FORCEFILESYSTEM = None  # port: surface stub

FOS_NOCHANGEDIR = None  # port: surface stub

FOS_PICKFOLDERS = None  # port: surface stub

HRESULT_CANCELLED = None  # port: surface stub

def runFolderDialog(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``runFolderDialog``."""
    raise NotImplementedError("port runFolderDialog from host/directory-picker-native/src/win32-dialog-logic.ts")

class Win32DialogBindings(Protocol):
    """Surface stub for upstream interface ``Win32DialogBindings``."""
    pass

class Win32FolderDialog(Protocol):
    """Surface stub for upstream interface ``Win32FolderDialog``."""
    pass
