"""Auto-generated surface skeleton for upstream ``workflow/workflow-worker-thread/src/host.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workflow/workflow-worker-thread/src/host.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WorkerRun",
    "workerSpawnEnv",
]

def workerSpawnEnv(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``workerSpawnEnv``."""
    raise NotImplementedError("port workerSpawnEnv from workflow/workflow-worker-thread/src/host.ts")

class WorkerRun:
    """Surface stub for upstream class ``WorkerRun``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkerRun.__init__ from workflow/workflow-worker-thread/src/host.ts")
