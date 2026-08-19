"""Auto-generated surface skeleton for upstream ``goal/goal/src/runtime.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``goal/goal/src/runtime.ts``
"""


from __future__ import annotations

__all__: list[str] = [
    "GOAL_CHANGE_VERSION",
    "GoalError",
    "GoalId",
]

GOAL_CHANGE_VERSION = None  # port: surface stub

def GoalId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``GoalId``."""
    raise NotImplementedError("port GoalId from goal/goal/src/runtime.ts")

class GoalError:
    """Surface stub for upstream class ``GoalError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port GoalError.__init__ from goal/goal/src/runtime.ts")
