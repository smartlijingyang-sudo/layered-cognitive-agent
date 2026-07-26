"""第5.8节：人工审批（HITL）契约。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from contracts.decision import StructuredDecision


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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
    approver: Optional[str] = None
    comment: Optional[str] = None
    decided_at: datetime = field(default_factory=_now)
