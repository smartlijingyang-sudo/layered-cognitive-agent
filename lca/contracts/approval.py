"""第5.8节：人工审批（HITL）契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lca.contracts.decision import StructuredDecision


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ApprovalRequest:
    request_id: str
    trace_id: str
    step: int
    risk_reason: str
    pending_decision: StructuredDecision
    created_at: datetime = field(default_factory=_now)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalDecision:
    request_id: str
    approved: bool
    approver: str | None = None
    comment: str | None = None
    decided_at: datetime = field(default_factory=_now)
