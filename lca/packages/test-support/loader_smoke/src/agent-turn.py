"""Auto-generated surface skeleton for upstream ``test-support/loader-smoke/src/agent-turn.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/loader-smoke/src/agent-turn.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FixtureTurnOptions",
    "FixtureTurnResult",
    "runFixtureTurn",
]

def runFixtureTurn(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``runFixtureTurn``."""
    raise NotImplementedError("port runFixtureTurn from test-support/loader-smoke/src/agent-turn.ts")

class FixtureTurnOptions(Protocol):
    """Surface stub for upstream interface ``FixtureTurnOptions``."""
    pass

class FixtureTurnResult(Protocol):
    """Surface stub for upstream interface ``FixtureTurnResult``."""
    pass
