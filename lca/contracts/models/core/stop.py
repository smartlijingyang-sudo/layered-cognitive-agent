"""StopReason / StopDecision —— 停止阶段使用的数据契约。

``StopPolicy`` 是 State 群内的策略接口，见
``lca.contracts.protocols.runtime.StopPolicy``。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from lca.contracts.models.core.lifecycle import TaskStatus


class StopReason(Enum):
    """Why the loop stopped (or continues)."""

    CONTINUE = "continue"
    BUDGET_EXCEEDED = "budget_exceeded"
    TASK_COMPLETED = "task_completed"
    ERROR = "error"


@dataclass(frozen=True)
class StopDecision:
    """Loop's only stop signal — continue or halt with reason/output/status."""

    should_stop: bool = False
    reason: StopReason = StopReason.CONTINUE
    final_output: str | None = None
    status: TaskStatus | None = None
