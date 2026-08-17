"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/input/decorations.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/input/decorations.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ChipRender",
    "DraftDecorations",
    "TextRefRange",
    "TokenRange",
    "deriveDecorations",
    "scanTextRefs",
]

def deriveDecorations(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveDecorations``."""
    raise NotImplementedError("port deriveDecorations from client/ui-conversation/src/client/input/decorations.ts")

def scanTextRefs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scanTextRefs``."""
    raise NotImplementedError("port scanTextRefs from client/ui-conversation/src/client/input/decorations.ts")

class ChipRender(Protocol):
    """Surface stub for upstream interface ``ChipRender``."""
    pass

class DraftDecorations(Protocol):
    """Surface stub for upstream interface ``DraftDecorations``."""
    pass

class TextRefRange(Protocol):
    """Surface stub for upstream interface ``TextRefRange``."""
    pass

class TokenRange(Protocol):
    """Surface stub for upstream interface ``TokenRange``."""
    pass
