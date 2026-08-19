"""Auto-generated surface skeleton for upstream ``workflow/workflow-worker-thread/src/runtime.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workflow/workflow-worker-thread/src/runtime.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "ExecutionObserver",
    "WorkflowExecution",
]

class WorkflowExecution:
    """Surface stub for upstream class ``WorkflowExecution``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkflowExecution.__init__ from workflow/workflow-worker-thread/src/runtime.ts")

class ExecutionObserver(Protocol):
    """Surface stub for upstream interface ``ExecutionObserver``."""
    pass
