"""StopReason / StopDecision / StopOutcome —— 认知循环停止判定数据契约。

``StopRule`` 是能力接口，见 ``lca.contracts.protocols.runtime.StopRule``。
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


# Backwards-compat alias — C3 removed StopOutcome in favour of
# StopDecision (StopOutcomePolicy renamed to StopPolicy returning StopDecision).
# Downstream code on this branch (lca.contracts.protocols.runtime.StopOutcomePolicy,
# lca.contracts.__init__ re-exports) still references the old name. Restore
# as a thin alias to keep the tree importing until C4 lands main's
# StopPolicy shape (per ADR-0103 §4 cross-cluster follow-up pattern,
# mirrors commit 945cc3ba restoring DECISION_GATE post-C1-port).
StopOutcome = StopDecision


@dataclass(frozen=True)
class StopOutcome:
    """单步结果判定（StopOutcomePolicy）的返回类型。

    仅 StopOutcomePolicy 实现与 StopRule 内部使用；循环边界对外统一用
    StopDecision（见 lca.contracts.protocols.runtime.StopRule）。
    """

    should_stop: bool = False
    final_output: str | None = None
    status: TaskStatus | None = None
