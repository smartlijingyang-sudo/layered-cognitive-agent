"""第5.10节：运行结果与异常契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from lca.contracts.state import Budget


@dataclass
class Result:
    trace_id: str
    status: Literal["completed", "failed", "paused", "waiting_human"]
    final_state_ref: str
    total_steps: int
    budget_used: Budget
    schema_version: str = "1.0"
    output: str | None = None
    lessons: list[str] = field(default_factory=list)
    trace_url: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ApprovalPendingError(Exception):
    def __init__(self, approval_request: Any):
        self.approval_request = approval_request
        super().__init__("waiting for human approval")


class BudgetExceededError(Exception):
    pass


class ToolExecutionError(Exception):
    def __init__(self, message: str, last_observation: Any | None = None):
        self.last_observation = last_observation
        super().__init__(message)
