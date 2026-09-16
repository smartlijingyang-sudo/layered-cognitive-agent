"""StopReason / StopDecision — the loop's terminal payload contract.

The loop terminator is a four-field struct built by `TerminateStrategy`
(the `binding: terminate` strategy behind the outer plan's
`terminal.commit` node) from the model's own `decision.action_type` /
`decision.response_text`, from `act.observe.terminate_decide`'s
`should_terminate` port, or from the budget guard. There is no host-side
policy class and no `should_stop` boolean. ADR-0094 previously owned the
StopPolicy seam; that seam is retired per plan
`docs/plans/2026-09-14-stop-decision-retirement.md`. Termination rules:
`docs/specs/tool-failure-recovery.md` §7.
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
    - `act.observe.terminate_decide` emits `should_terminate` when the
      receipt carries no `failure_kind` (the host never dispatched the
      effect); `TerminateStrategy` then reads the failed `act_outcome`
      as `reason="error"`, which the driver maps to ERROR. A classified
      `failure_kind` is the tool's report about its own subject and goes
      back to the model instead — see
      `docs/specs/tool-failure-recovery.md` §3/§7
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
