"""Auto-generated surface skeleton for upstream ``host/directory-picker-native/src/win32-dialog.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker-native/src/win32-dialog.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DIALOG_TITLE",
    "Win32DialogInternals",
    "Win32DialogWorkerLike",
    "pickWin32Directory",
]

DIALOG_TITLE = None  # port: surface stub

def pickWin32Directory(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``pickWin32Directory``."""
    raise NotImplementedError("port pickWin32Directory from host/directory-picker-native/src/win32-dialog.ts")

class Win32DialogInternals(Protocol):
    """Surface stub for upstream interface ``Win32DialogInternals``."""
    pass

class Win32DialogWorkerLike(Protocol):
    """Surface stub for upstream interface ``Win32DialogWorkerLike``."""
    pass
