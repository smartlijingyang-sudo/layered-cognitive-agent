"""Auto-generated surface skeleton for upstream ``goal/tool-goal/src/authority.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``goal/tool-goal/src/authority.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "GoalToolAuthority",
    "GoalToolExecution",
    "completionAuthority",
    "goalToolExecution",
    "requireDirectHuman",
]

GoalToolAuthority: TypeAlias = object  # port: surface stub

def completionAuthority(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``completionAuthority``."""
    raise NotImplementedError("port completionAuthority from goal/tool-goal/src/authority.ts")

def goalToolExecution(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``goalToolExecution``."""
    raise NotImplementedError("port goalToolExecution from goal/tool-goal/src/authority.ts")

def requireDirectHuman(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``requireDirectHuman``."""
    raise NotImplementedError("port requireDirectHuman from goal/tool-goal/src/authority.ts")

class GoalToolExecution(Protocol):
    """Surface stub for upstream interface ``GoalToolExecution``."""
    pass
