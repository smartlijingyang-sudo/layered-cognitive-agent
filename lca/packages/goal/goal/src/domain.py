"""Auto-generated surface skeleton for upstream ``goal/goal/src/domain.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``goal/goal/src/domain.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FoldedGoal",
    "GoalChangeMeta",
    "GoalChanged",
    "GoalClearChangeMeta",
    "GoalErrorCode",
    "GoalMessageSource",
    "GoalOperation",
    "GoalSnapshotChangeMeta",
]

GoalChangeMeta: TypeAlias = object  # port: surface stub

GoalErrorCode: TypeAlias = object  # port: surface stub

GoalOperation: TypeAlias = object  # port: surface stub

class FoldedGoal(Protocol):
    """Surface stub for upstream interface ``FoldedGoal``."""
    pass

class GoalChanged(Protocol):
    """Surface stub for upstream interface ``GoalChanged``."""
    pass

class GoalClearChangeMeta(Protocol):
    """Surface stub for upstream interface ``GoalClearChangeMeta``."""
    pass

class GoalMessageSource(Protocol):
    """Surface stub for upstream interface ``GoalMessageSource``."""
    pass

class GoalSnapshotChangeMeta(Protocol):
    """Surface stub for upstream interface ``GoalSnapshotChangeMeta``."""
    pass
