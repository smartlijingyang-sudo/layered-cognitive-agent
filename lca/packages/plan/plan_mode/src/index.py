"""Auto-generated surface skeleton for upstream ``plan/plan-mode/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``plan/plan-mode/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "EXIT_PLAN_MODE",
    "PlanModeConfig",
    "PlanModeController",
    "foldPlanMode",
    "resolveConfig",
]

EXIT_PLAN_MODE = None  # port: surface stub

def foldPlanMode(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``foldPlanMode``."""
    raise NotImplementedError("port foldPlanMode from plan/plan-mode/src/index.ts")

def resolveConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveConfig``."""
    raise NotImplementedError("port resolveConfig from plan/plan-mode/src/index.ts")

class PlanModeController:
    """Surface stub for upstream class ``PlanModeController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PlanModeController.__init__ from plan/plan-mode/src/index.ts")

class PlanModeConfig(Protocol):
    """Surface stub for upstream interface ``PlanModeConfig``."""
    pass
