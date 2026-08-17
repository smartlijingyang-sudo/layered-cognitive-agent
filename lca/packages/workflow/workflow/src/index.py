"""Auto-generated surface skeleton for upstream ``workflow/workflow/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workflow/workflow/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WorkflowAgentEndInfo",
    "WorkflowAgentInfo",
    "WorkflowAgentOutcome",
    "WorkflowEngine",
    "WorkflowError",
    "WorkflowErrorCode",
    "WorkflowEventName",
    "WorkflowMeta",
    "WorkflowPhase",
    "WorkflowResult",
    "WorkflowResultInfo",
    "WorkflowRun",
    "WorkflowRunId",
    "WorkflowRunInfo",
    "WorkflowStartRequest",
    "WorkflowStopReason",
    "isFatalWorkflowError",
]

WorkflowAgentEndInfo: TypeAlias = object  # port: surface stub

WorkflowAgentInfo: TypeAlias = object  # port: surface stub

WorkflowAgentOutcome: TypeAlias = object  # port: surface stub

WorkflowErrorCode: TypeAlias = object  # port: surface stub

WorkflowEventName: TypeAlias = object  # port: surface stub

WorkflowMeta: TypeAlias = object  # port: surface stub

WorkflowPhase: TypeAlias = object  # port: surface stub

WorkflowResult: TypeAlias = object  # port: surface stub

WorkflowResultInfo: TypeAlias = object  # port: surface stub

WorkflowRun: TypeAlias = object  # port: surface stub

WorkflowRunInfo: TypeAlias = object  # port: surface stub

WorkflowStartRequest: TypeAlias = object  # port: surface stub

WorkflowStopReason: TypeAlias = object  # port: surface stub

def isFatalWorkflowError(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isFatalWorkflowError``."""
    raise NotImplementedError("port isFatalWorkflowError from workflow/workflow/src/index.ts")

class WorkflowEngine:
    """Surface stub for upstream class ``WorkflowEngine``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkflowEngine.__init__ from workflow/workflow/src/index.ts")

class WorkflowError:
    """Surface stub for upstream class ``WorkflowError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkflowError.__init__ from workflow/workflow/src/index.ts")

WorkflowRunId = None  # port: surface stub (reexport)
