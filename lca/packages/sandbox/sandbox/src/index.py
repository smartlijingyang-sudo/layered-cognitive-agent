"""Auto-generated surface skeleton for upstream ``sandbox/sandbox/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ESCALATION_TARGETS",
    "SANDBOX_UNAVAILABLE",
    "WIDER_MODES",
    "ConfinedArgv",
    "ConfinedSandboxMode",
    "EscalationApproval",
    "EscalationApprover",
    "EscalationOutcome",
    "EscalationRequest",
    "RunnerFailureRule",
    "SandboxEnforcement",
    "SandboxExecutionPolicy",
    "SandboxMode",
    "SandboxPolicy",
    "SandboxProvider",
    "SandboxUnavailableError",
    "approveEscalation",
    "canonicalPath",
    "escalationHintMarker",
    "sandboxDenialMarker",
    "validateEscalationArgs",
    "writableRoots",
]

ConfinedSandboxMode: TypeAlias = object  # port: surface stub

EscalationApproval: TypeAlias = object  # port: surface stub

EscalationApprover: TypeAlias = object  # port: surface stub

EscalationOutcome: TypeAlias = object  # port: surface stub

EscalationRequest: TypeAlias = object  # port: surface stub

SandboxEnforcement: TypeAlias = object  # port: surface stub

SandboxMode: TypeAlias = object  # port: surface stub

SANDBOX_UNAVAILABLE = None  # port: surface stub

class SandboxProvider:
    """Surface stub for upstream class ``SandboxProvider``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SandboxProvider.__init__ from sandbox/sandbox/src/index.ts")

class SandboxUnavailableError:
    """Surface stub for upstream class ``SandboxUnavailableError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SandboxUnavailableError.__init__ from sandbox/sandbox/src/index.ts")

ESCALATION_TARGETS = None  # port: surface stub (reexport)

WIDER_MODES = None  # port: surface stub (reexport)

approveEscalation = None  # port: surface stub (reexport)

canonicalPath = None  # port: surface stub (reexport)

escalationHintMarker = None  # port: surface stub (reexport)

sandboxDenialMarker = None  # port: surface stub (reexport)

validateEscalationArgs = None  # port: surface stub (reexport)

writableRoots = None  # port: surface stub (reexport)

class ConfinedArgv(Protocol):
    """Surface stub for upstream interface ``ConfinedArgv``."""
    pass

class RunnerFailureRule(Protocol):
    """Surface stub for upstream interface ``RunnerFailureRule``."""
    pass

class SandboxExecutionPolicy(Protocol):
    """Surface stub for upstream interface ``SandboxExecutionPolicy``."""
    pass

class SandboxPolicy(Protocol):
    """Surface stub for upstream interface ``SandboxPolicy``."""
    pass
