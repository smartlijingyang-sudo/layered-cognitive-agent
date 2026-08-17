"""Auto-generated surface skeleton for upstream ``client/ui-workflow-run/src/client/workflow-definition.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-workflow-run/src/client/workflow-definition.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WorkflowRunChatData",
    "WorkflowRunMemberData",
    "WorkflowRunPhaseData",
    "WorkflowRunStatus",
    "workflowPhaseKey",
    "workflowRunDefinition",
]

WorkflowRunStatus: TypeAlias = object  # port: surface stub

workflowRunDefinition = None  # port: surface stub

def workflowPhaseKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``workflowPhaseKey``."""
    raise NotImplementedError("port workflowPhaseKey from client/ui-workflow-run/src/client/workflow-definition.ts")

class WorkflowRunChatData(Protocol):
    """Surface stub for upstream interface ``WorkflowRunChatData``."""
    pass

class WorkflowRunMemberData(Protocol):
    """Surface stub for upstream interface ``WorkflowRunMemberData``."""
    pass

class WorkflowRunPhaseData(Protocol):
    """Surface stub for upstream interface ``WorkflowRunPhaseData``."""
    pass
