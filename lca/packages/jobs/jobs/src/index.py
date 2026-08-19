"""Auto-generated surface skeleton for upstream ``jobs/jobs/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``jobs/jobs/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "JobDoneListener",
    "JobHooks",
    "JobId",
    "JobKind",
    "JobKindMap",
    "JobOutcome",
    "JobRead",
    "JobRegistry",
    "JobSnapshot",
    "JobStart",
    "JobStatus",
    "JobsChangedListener",
]

JobDoneListener: TypeAlias = object  # port: surface stub

JobHooks: TypeAlias = object  # port: surface stub

JobKind: TypeAlias = object  # port: surface stub

JobKindMap: TypeAlias = object  # port: surface stub

JobOutcome: TypeAlias = object  # port: surface stub

JobRead: TypeAlias = object  # port: surface stub

JobSnapshot: TypeAlias = object  # port: surface stub

JobStart: TypeAlias = object  # port: surface stub

JobStatus: TypeAlias = object  # port: surface stub

JobsChangedListener: TypeAlias = object  # port: surface stub

class JobRegistry:
    """Surface stub for upstream class ``JobRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port JobRegistry.__init__ from jobs/jobs/src/index.ts")

JobId = None  # port: surface stub (reexport)
