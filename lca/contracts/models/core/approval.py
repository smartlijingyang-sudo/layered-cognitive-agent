"""第5.8节：人工审批（HITL）契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lca.contracts.atoms.ids import utc_now
from lca.contracts.models.core.decision import Decision


@dataclass
class ApprovalRequest:
    """人工审批请求：携带待审批的 Decision 及上下文。"""

    request_id: str
    trace_id: str
    step: int
    risk_reason: str
    pending_decision: Decision
    created_at: datetime = field(default_factory=utc_now)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalDecision:
    """人工审批结果：approved + 可选批注。"""

    request_id: str
    approved: bool
    approver: str | None = None
    comment: str | None = None
    decided_at: datetime = field(default_factory=utc_now)
