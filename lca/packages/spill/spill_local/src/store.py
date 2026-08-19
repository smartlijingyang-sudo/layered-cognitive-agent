"""Auto-generated surface skeleton for upstream ``spill/spill-local/src/store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``spill/spill-local/src/store.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SaveTextOptions",
    "SavedText",
    "encodeSegment",
    "privateRoot",
    "saveTextFile",
    "sessionDir",
]

def encodeSegment(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``encodeSegment``."""
    raise NotImplementedError("port encodeSegment from spill/spill-local/src/store.ts")

def privateRoot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``privateRoot``."""
    raise NotImplementedError("port privateRoot from spill/spill-local/src/store.ts")

def saveTextFile(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``saveTextFile``."""
    raise NotImplementedError("port saveTextFile from spill/spill-local/src/store.ts")

def sessionDir(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sessionDir``."""
    raise NotImplementedError("port sessionDir from spill/spill-local/src/store.ts")

class SaveTextOptions(Protocol):
    """Surface stub for upstream interface ``SaveTextOptions``."""
    pass

class SavedText(Protocol):
    """Surface stub for upstream interface ``SavedText``."""
    pass
