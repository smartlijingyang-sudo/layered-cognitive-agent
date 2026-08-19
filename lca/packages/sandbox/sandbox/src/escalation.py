"""Auto-generated surface skeleton for upstream ``sandbox/sandbox/src/escalation.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox/src/escalation.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ESCALATION_TARGETS",
    "WIDER_MODES",
    "EscalationApproval",
    "EscalationApprover",
    "EscalationOutcome",
    "EscalationRequest",
    "approveEscalation",
    "escalationHintMarker",
    "sandboxDenialMarker",
    "validateEscalationArgs",
]

EscalationOutcome: TypeAlias = object  # port: surface stub

ESCALATION_TARGETS = None  # port: surface stub

WIDER_MODES = None  # port: surface stub

def approveEscalation(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``approveEscalation``."""
    raise NotImplementedError("port approveEscalation from sandbox/sandbox/src/escalation.ts")

def escalationHintMarker(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``escalationHintMarker``."""
    raise NotImplementedError("port escalationHintMarker from sandbox/sandbox/src/escalation.ts")

def sandboxDenialMarker(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sandboxDenialMarker``."""
    raise NotImplementedError("port sandboxDenialMarker from sandbox/sandbox/src/escalation.ts")

def validateEscalationArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``validateEscalationArgs``."""
    raise NotImplementedError("port validateEscalationArgs from sandbox/sandbox/src/escalation.ts")

class EscalationApproval(Protocol):
    """Surface stub for upstream interface ``EscalationApproval``."""
    pass

class EscalationApprover(Protocol):
    """Surface stub for upstream interface ``EscalationApprover``."""
    pass

class EscalationRequest(Protocol):
    """Surface stub for upstream interface ``EscalationRequest``."""
    pass
