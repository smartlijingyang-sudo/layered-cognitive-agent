"""Auto-generated surface skeleton for upstream ``workflow/workflow-worker-thread/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workflow/workflow-worker-thread/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ChildHandle",
    "ChildPort",
    "ChildResult",
    "ChildStartRequest",
    "Config",
    "MaterializeError",
    "WorkerInit",
    "WorkerLimits",
    "WorkerThreadWorkflowEngine",
    "materializeFromRealm",
    "validateMeta",
]

ChildHandle: TypeAlias = object  # port: surface stub

ChildPort: TypeAlias = object  # port: surface stub

ChildResult: TypeAlias = object  # port: surface stub

ChildStartRequest: TypeAlias = object  # port: surface stub

WorkerInit: TypeAlias = object  # port: surface stub

WorkerLimits: TypeAlias = object  # port: surface stub

class WorkerThreadWorkflowEngine:
    """Surface stub for upstream class ``WorkerThreadWorkflowEngine``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkerThreadWorkflowEngine.__init__ from workflow/workflow-worker-thread/src/index.ts")

MaterializeError = None  # port: surface stub (reexport)

materializeFromRealm = None  # port: surface stub (reexport)

validateMeta = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
