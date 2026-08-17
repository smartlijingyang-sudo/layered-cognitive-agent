"""Auto-generated surface skeleton for upstream ``workflow/workflow-worker-thread/src/protocol.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workflow/workflow-worker-thread/src/protocol.ts``
"""


from __future__ import annotations
import enum
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "HostToWorkerMessage",
    "HostToWorkerPayloads",
    "HostToWorkerType",
    "WorkerToHostMessage",
    "WorkerToHostPayloads",
    "WorkerToHostType",
]

HostToWorkerMessage: TypeAlias = object  # port: surface stub

WorkerToHostMessage: TypeAlias = object  # port: surface stub

class HostToWorkerType(enum.Enum):
    """Surface stub for upstream enum ``HostToWorkerType``."""
    pass

class WorkerToHostType(enum.Enum):
    """Surface stub for upstream enum ``WorkerToHostType``."""
    pass

class HostToWorkerPayloads(Protocol):
    """Surface stub for upstream interface ``HostToWorkerPayloads``."""
    pass

class WorkerToHostPayloads(Protocol):
    """Surface stub for upstream interface ``WorkerToHostPayloads``."""
    pass
