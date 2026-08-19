"""Auto-generated surface skeleton for upstream ``workflow/workflow/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workflow/workflow/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WorkflowAgentEndInfo",
    "WorkflowAgentInfo",
    "WorkflowAgentOutcome",
    "WorkflowMeta",
    "WorkflowPhase",
    "WorkflowResult",
    "WorkflowResultInfo",
    "WorkflowRunId",
    "WorkflowRunInfo",
    "WorkflowStopReason",
]

WorkflowAgentOutcome: TypeAlias = object  # port: surface stub

WorkflowRunId: TypeAlias = object  # port: surface stub

WorkflowStopReason: TypeAlias = object  # port: surface stub

class WorkflowAgentEndInfo(Protocol):
    """Surface stub for upstream interface ``WorkflowAgentEndInfo``."""
    pass

class WorkflowAgentInfo(Protocol):
    """Surface stub for upstream interface ``WorkflowAgentInfo``."""
    pass

class WorkflowMeta(Protocol):
    """Surface stub for upstream interface ``WorkflowMeta``."""
    pass

class WorkflowPhase(Protocol):
    """Surface stub for upstream interface ``WorkflowPhase``."""
    pass

class WorkflowResult(Protocol):
    """Surface stub for upstream interface ``WorkflowResult``."""
    pass

class WorkflowResultInfo(Protocol):
    """Surface stub for upstream interface ``WorkflowResultInfo``."""
    pass

class WorkflowRunInfo(Protocol):
    """Surface stub for upstream interface ``WorkflowRunInfo``."""
    pass
