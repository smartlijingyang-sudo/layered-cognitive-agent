"""Cross-layer pure data types — no behaviour protocols."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.decision import ActResult, Decision, Reflection
from lca.contracts.lifecycle import TaskStatus


@dataclass
class Turn:
    """One cognitive step: decision + act result + optional reflection."""

    decision: Decision
    observation: ActResult
    reflection: Reflection | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def act_result(self) -> ActResult:
        return self.observation


@dataclass
class StopOutcome:
    """Internal step-outcome used only inside DefaultStopRule (not public dual).

    Prefer StopDecision from lca.contracts.stop for the loop boundary.
    """

    should_stop: bool = False
    final_output: str | None = None
    status: TaskStatus | None = None


# Keep name used by legacy imports; loop boundary uses StopDecision.
StepOutcome = StopOutcome


@dataclass
class TeamAssignment:
    """Deprecated team assignment unit — prefer process strategies.

    # DEPRECATED: remove after one release cycle if unused.
    """

    member_id: str
    objective: str
    depends_on: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
