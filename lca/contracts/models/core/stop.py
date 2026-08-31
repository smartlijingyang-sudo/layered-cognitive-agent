"""StopReason / StopDecision —— 停止阶段使用的数据契约。

``StopPolicy`` 是 State 群内的策略接口，见
``lca.contracts.protocols.runtime.StopPolicy``。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from lca.contracts.models.core.lifecycle import TaskStatus

if TYPE_CHECKING:
    from lca.runtime.diagnostic import RunDiagnostic


class StopReason(Enum):
    """Why the loop stopped (or continues)."""

    CONTINUE = "continue"
    BUDGET_EXCEEDED = "budget_exceeded"
    TASK_COMPLETED = "task_completed"
    ERROR = "error"


@dataclass(frozen=True)
class StopDecision:
    """Loop's only stop signal — continue or halt with reason/output/status.

    ADR-0122: ``final_output`` carries the successful answer when
    ``reason == TASK_COMPLETED``; ``failure`` carries a typed :class:`RunDiagnostic`
    when ``reason == ERROR``. The reducer / TerminalOutcome consumes one of
    the two — never both — so consumers do not have to disambiguate by
    string heuristics.
    """

    should_stop: bool = False
    reason: StopReason = StopReason.CONTINUE
    final_output: str | None = None
    status: TaskStatus | None = None
    failure: RunDiagnostic | None = None
