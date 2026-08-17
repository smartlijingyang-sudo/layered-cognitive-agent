"""Auto-generated surface skeleton for upstream ``extensions/ui-cordis/src/client/card-model.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/ui-cordis/src/client/card-model.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CordisActionCard",
    "CordisDefineCard",
    "CordisRunCard",
    "CordisToolState",
    "cordisActionCard",
    "cordisDefineCard",
    "cordisRunCard",
]

CordisToolState: TypeAlias = object  # port: surface stub

def cordisActionCard(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``cordisActionCard``."""
    raise NotImplementedError("port cordisActionCard from extensions/ui-cordis/src/client/card-model.ts")

def cordisDefineCard(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``cordisDefineCard``."""
    raise NotImplementedError("port cordisDefineCard from extensions/ui-cordis/src/client/card-model.ts")

def cordisRunCard(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``cordisRunCard``."""
    raise NotImplementedError("port cordisRunCard from extensions/ui-cordis/src/client/card-model.ts")

class CordisActionCard(Protocol):
    """Surface stub for upstream interface ``CordisActionCard``."""
    pass

class CordisDefineCard(Protocol):
    """Surface stub for upstream interface ``CordisDefineCard``."""
    pass

class CordisRunCard(Protocol):
    """Surface stub for upstream interface ``CordisRunCard``."""
    pass
