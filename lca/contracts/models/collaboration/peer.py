"""Peer assistant and collaboration contract models.

Aligned with ADR-0250, ADR-0042, and ADR-0228.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


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


class FoldedDelegationResult(BaseModel):
    """Structured result synthesized by the delegate.fold node."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    member_findings: dict[str, str]
    synthesized_verdict: str
    consensus_status: Literal["unanimous", "concerns_noted", "split"]
