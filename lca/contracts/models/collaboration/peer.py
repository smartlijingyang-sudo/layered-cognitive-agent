"""Peer assistant and collaboration contract models.

Aligned with ADR-0250, ADR-0042, and ADR-0228.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PeerProfile(BaseModel):
    """Persistent peer specialist profile mapping to an AssistantHome."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    peer_id: str
    name: str
    role: str
    description: str
    home_namespace: str
    capabilities: tuple[str, ...] = ()


class HandoffEnvelope(BaseModel):
    """Asynchronous handoff delegation envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: str
    sender_id: str
    receiver_id: str
    intent: Literal["consult", "delegate", "review", "fold"]
    objective: str
    context_slice: dict[str, Any]
    priority: bool = False
    timeout_ms: int = 60000


class RoomSpec(BaseModel):
    """Collaboration room specification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    room_id: str
    display_name: str
    coordinator_agent_id: str
    member_peer_ids: tuple[str, ...]
    shared_topic_id: str
    routing_policy: Literal["coordinator_first", "mention_only"] = "coordinator_first"


class PeerFoldedResult(BaseModel):
    """Structured result synthesized by the delegate.fold node (ADR-0250)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    member_findings: dict[str, str]
    synthesized_verdict: str
    consensus_status: Literal["unanimous", "concerns_noted", "split"]
    member_metadata: dict[str, dict[str, str]] = {}


class RoomMessageKind(StrEnum):
    """Kind of a room transcript message (room runtime go-live M1)."""

    USER = "user"
    RUN_STARTED = "run_started"
    PEER = "peer"
    FOLDED = "folded"
    APPROVAL = "approval"


class RoomMessage(BaseModel):
    """Immutable room transcript fact (ADR-0250 room runtime).

    ``correlation_id`` ties one collaboration round; ``run_id`` references the
    real dispatched run. Appended by the room message store only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str
    room_id: str
    kind: RoomMessageKind
    sender_id: str
    content: str
    correlation_id: str = ""
    run_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int


# Backward-compatible alias to avoid breaking existing references
FoldedDelegationResult = PeerFoldedResult

__all__ = [
    "FoldedDelegationResult",
    "HandoffEnvelope",
    "PeerFoldedResult",
    "PeerProfile",
    "RoomMessage",
    "RoomMessageKind",
    "RoomSpec",
]
