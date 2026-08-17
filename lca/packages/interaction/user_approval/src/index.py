"""Auto-generated surface skeleton for upstream ``interaction/user-approval/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``interaction/user-approval/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "APPROVAL_POLICIES",
    "ApprovalOutcome",
    "ApprovalPolicy",
    "ApprovalRequest",
    "ApprovalRequestId",
    "ApprovalService",
    "Config",
    "effectiveApprovalPolicy",
    "setApprovalPolicy",
]

ApprovalOutcome: TypeAlias = object  # port: surface stub

ApprovalPolicy: TypeAlias = object  # port: surface stub

APPROVAL_POLICIES = None  # port: surface stub

def effectiveApprovalPolicy(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``effectiveApprovalPolicy``."""
    raise NotImplementedError("port effectiveApprovalPolicy from interaction/user-approval/src/index.ts")

def setApprovalPolicy(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``setApprovalPolicy``."""
    raise NotImplementedError("port setApprovalPolicy from interaction/user-approval/src/index.ts")

class ApprovalService:
    """Surface stub for upstream class ``ApprovalService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ApprovalService.__init__ from interaction/user-approval/src/index.ts")

ApprovalRequestId = None  # port: surface stub (reexport)

class ApprovalRequest(Protocol):
    """Surface stub for upstream interface ``ApprovalRequest``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
