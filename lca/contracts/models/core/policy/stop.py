"""StopReason / StopDecision — the loop's terminal payload contract.

The loop terminator is a four-field struct produced by the model itself
(via `TerminalCommitExecutor` reading `decision.action_type` and
`decision.response_text`) or by Body raising `DeterministicToolError`,
or by the budget guard. There is no host-side policy class and no
`should_stop` boolean. ADR-0094 previously owned the StopPolicy seam;
that seam is retired per plan
`docs/plans/2026-09-14-stop-decision-retirement.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from lca.contracts.models.core.state.lifecycle import TaskStatus

if TYPE_CHECKING:
    from lca.runtime.support.diagnostic import RunDiagnostic


class StopReason(Enum):
    """Why the loop reached a terminal state.

    The model never produces a stop reason directly. The producer of
    `StopDecision.reason` is one of three typed sites:
    - model RESPOND with non-empty response_text maps to a terminal
      payload (the model is the implicit source of "done")
    - Body raises DeterministicToolError on `failure_kind == execution`,
      and the outer driver maps it to ERROR
    - the budget guard produces BUDGET_EXCEEDED when AgentState.budget is exhausted (per ADR-0225, the prior ``max_visits`` per-node ceiling is gone)
    """

    CONTINUE = "continue"
    BUDGET_EXCEEDED = "budget_exceeded"
    ERROR = "error"


@dataclass(frozen=True)
class StopDecision:
    """Loop's terminal payload — applied by the reducer's apply_stop.

    ADR-0122: ``final_output`` carries the successful answer when the
    model produced RESPOND with non-empty text; ``failure`` carries a
    typed :class:`RunDiagnostic` when ``reason == ERROR``. The reducer
    consumes one of the two, never both, so consumers do not have to
    disambiguate by string heuristics.
    """

    reason: StopReason = StopReason.CONTINUE
    final_output: str | None = None
    status: TaskStatus | None = None
    failure: RunDiagnostic | None = None
