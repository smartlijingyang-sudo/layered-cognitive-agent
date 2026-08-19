"""Auto-generated surface skeleton for upstream ``code-runtime/code-runtime-worker-thread/src/protocol.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``code-runtime/code-runtime-worker-thread/src/protocol.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DoneMessage",
    "ReplyMessage",
    "WorkerBootData",
    "WorkerToHost",
]

ReplyMessage: TypeAlias = object  # port: surface stub

WorkerToHost: TypeAlias = object  # port: surface stub

class DoneMessage(Protocol):
    """Surface stub for upstream interface ``DoneMessage``."""
    pass

class WorkerBootData(Protocol):
    """Surface stub for upstream interface ``WorkerBootData``."""
    pass
