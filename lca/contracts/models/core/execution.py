"""ExecutionEnvelope — the hand-plane narrow gate contract (PR6 / v3 §9).

Every tool / delegation / message that touches the world passes through
``ExecutionEnvelope``.  The envelope carries:

- identity (``invocation_id``)
- provenance (``decision_id``, ``principal``, ``provenance``)
- capability grant (``capability_grant``)
- idempotency (``idempotency_key``)
- budget / deadline (``budget_reservation``, ``deadline_ts``)
- approval (``approval_requirement``, ``risk_level``, ``risk_factors``)
- resource scope / amount / time window (D6/§9.3 RiskLevel granularity)

v3 rules:
- ``Body.act`` requires an envelope before calling the executor.
- Default is **non-idempotent**, no cache, unless the tool declares
  idempotency via its spec.
- ``requires_approval=True`` tools never go through cache.
- Approval tokens are bound to the envelope via ``hash_params``;
  retry with mutated params invalidates the token.

This module is the data-contract layer.  Implementation lives in
``lca/layer1_cognitive/body/safe_executor.py`` and the approval processor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class RiskLevel(str, Enum):
    """Risk classification for an ExecutionEnvelope (v3 §9.3)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RiskFactor:
    """Single dimension of risk (v3 §9.3 RiskFactor)."""

    dimension: Literal[
        "action_type",
        "data_classification",
        "scope",
        "reversibility",
        "amount",
        "external_visibility",
    ]
    value: str
    severity: Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ExecutionEnvelope:
    """The single hand-plane gate contract (v3 §9.1 + §9.3).

    All fields are immutable; new envelopes are minted per invocation.
    """

    invocation_id: str
    decision_id: str
    principal: str
    capability_grant: tuple[str, ...]
    plane_ref: str
    tool_schema_version: str
    input_refs: tuple[str, ...] = ()
    idempotency_key: str = ""
    deadline_ts: float | None = None
    budget_reservation: str | None = None
    approval_requirement: str | None = None
    provenance: tuple[str, ...] = ()
    # Risk dimension (D6 / §9.3)
    risk_level: RiskLevel = RiskLevel.LOW
    risk_factors: tuple[RiskFactor, ...] = ()
    resource_scope: str | None = None
    amount: float | None = None
    time_window: tuple[float, float] | None = None
    preview_hash: str | None = None
    # Metadata
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalToken:
    """Approval bound to a specific ExecutionEnvelope (v3 §9.3 / §22).

    Once consumed, the token is invalidated.  Reuse is rejected by the
    executor.
    """

    approval_id: str
    invocation_id: str
    principal: str
    capability_grant: tuple[str, ...]
    resource_scope: str | None = None
    amount_limit: float | None = None
    time_window: tuple[float, float] | None = None
    expires_at: float = 0.0
    hash_params: str = ""
    issued_at: float = 0.0
    approver_role: str = ""


__all__ = [
    "ApprovalToken",
    "ExecutionEnvelope",
    "RiskFactor",
    "RiskLevel",
]
