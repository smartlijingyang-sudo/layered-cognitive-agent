"""Auto-generated surface skeleton for upstream ``jobs/jobs/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``jobs/jobs/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "JobDoneListener",
    "JobHooks",
    "JobId",
    "JobKind",
    "JobKindMap",
    "JobOutcome",
    "JobRead",
    "JobSnapshot",
    "JobStart",
    "JobStatus",
    "JobsChangedListener",
]

JobDoneListener: TypeAlias = object  # port: surface stub

JobKind: TypeAlias = object  # port: surface stub

JobStatus: TypeAlias = object  # port: surface stub

JobsChangedListener: TypeAlias = object  # port: surface stub

JobId = None  # port: surface stub (reexport)

class JobHooks(Protocol):
    """Surface stub for upstream interface ``JobHooks``."""
    pass

class JobKindMap(Protocol):
    """Surface stub for upstream interface ``JobKindMap``."""
    pass

class JobOutcome(Protocol):
    """Surface stub for upstream interface ``JobOutcome``."""
    pass

class JobRead(Protocol):
    """Surface stub for upstream interface ``JobRead``."""
    pass

class JobSnapshot(Protocol):
    """Surface stub for upstream interface ``JobSnapshot``."""
    pass

class JobStart(Protocol):
    """Surface stub for upstream interface ``JobStart``."""
    pass
