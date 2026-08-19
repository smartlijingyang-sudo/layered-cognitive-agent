"""Auto-generated surface skeleton for upstream ``client/ui-input-trigger/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-input-trigger/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ArbitrateKey",
    "ArbitrateOutcome",
    "BeginCommandRequest",
    "CandidateRequest",
    "ClientSessionContext",
    "CommandClaim",
    "ConsumeTokenRequest",
    "InputTriggerCandidate",
    "InputTriggerPick",
    "InputTriggerSource",
    "InsertReferenceRequest",
    "InsertTextRequest",
    "PickOutcome",
    "PickVia",
    "ReferenceCodec",
    "ReferenceInsert",
    "SubmitOutcome",
    "TokenSpan",
    "TriggerChar",
    "TriggerGuard",
    "TriggerPosition",
]

ArbitrateKey: TypeAlias = object  # port: surface stub

ArbitrateOutcome: TypeAlias = object  # port: surface stub

PickOutcome: TypeAlias = object  # port: surface stub

PickVia: TypeAlias = object  # port: surface stub

TriggerChar: TypeAlias = object  # port: surface stub

TriggerPosition: TypeAlias = object  # port: surface stub

class BeginCommandRequest(Protocol):
    """Surface stub for upstream interface ``BeginCommandRequest``."""
    pass

class CandidateRequest(Protocol):
    """Surface stub for upstream interface ``CandidateRequest``."""
    pass

class ClientSessionContext(Protocol):
    """Surface stub for upstream interface ``ClientSessionContext``."""
    pass

class CommandClaim(Protocol):
    """Surface stub for upstream interface ``CommandClaim``."""
    pass

class ConsumeTokenRequest(Protocol):
    """Surface stub for upstream interface ``ConsumeTokenRequest``."""
    pass

class InputTriggerCandidate(Protocol):
    """Surface stub for upstream interface ``InputTriggerCandidate``."""
    pass

class InputTriggerPick(Protocol):
    """Surface stub for upstream interface ``InputTriggerPick``."""
    pass

class InputTriggerSource(Protocol):
    """Surface stub for upstream interface ``InputTriggerSource``."""
    pass

class InsertReferenceRequest(Protocol):
    """Surface stub for upstream interface ``InsertReferenceRequest``."""
    pass

class InsertTextRequest(Protocol):
    """Surface stub for upstream interface ``InsertTextRequest``."""
    pass

class ReferenceCodec(Protocol):
    """Surface stub for upstream interface ``ReferenceCodec``."""
    pass

class ReferenceInsert(Protocol):
    """Surface stub for upstream interface ``ReferenceInsert``."""
    pass

class SubmitOutcome(Protocol):
    """Surface stub for upstream interface ``SubmitOutcome``."""
    pass

class TokenSpan(Protocol):
    """Surface stub for upstream interface ``TokenSpan``."""
    pass

class TriggerGuard(Protocol):
    """Surface stub for upstream interface ``TriggerGuard``."""
    pass
