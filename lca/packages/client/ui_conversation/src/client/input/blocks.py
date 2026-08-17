"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/input/blocks.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/input/blocks.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ComposerBlock",
    "ComposerBlockRegistry",
    "ComposerBlocks",
]

class ComposerBlockRegistry:
    """Surface stub for upstream class ``ComposerBlockRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ComposerBlockRegistry.__init__ from client/ui-conversation/src/client/input/blocks.ts")

class ComposerBlock(Protocol):
    """Surface stub for upstream interface ``ComposerBlock``."""
    pass

class ComposerBlocks(Protocol):
    """Surface stub for upstream interface ``ComposerBlocks``."""
    pass
