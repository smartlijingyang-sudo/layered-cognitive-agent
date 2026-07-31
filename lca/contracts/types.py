"""Cross-layer pure data types — no behaviour protocols."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.decision import Decision, Observation, Reflection
from lca.contracts.lifecycle import TaskStatus


@dataclass
class Turn:
    """One cognitive step: decision + act result + optional reflection."""

    decision: Decision
    observation: Observation
    reflection: Reflection | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def act_result(self) -> Observation:
        return self.observation


@dataclass
class StopOutcome:
    """Internal step-outcome used only inside DefaultStopRule (not public dual).

    Prefer StopDecision from lca.contracts.stop for the loop boundary.
    """

    should_stop: bool = False
    final_output: str | None = None
    status: TaskStatus | None = None


@dataclass
class TeamAssignment:
    """Deprecated team assignment unit — prefer process strategies."""

    member_id: str
    objective: str
    depends_on: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        import warnings

        warnings.warn(
            "'TeamAssignment' is deprecated, use process strategies instead",
            DeprecationWarning,
            stacklevel=2,
        )


def __getattr__(name: str) -> Any:
    if name == "StepOutcome":
        import warnings

        warnings.warn(
            "'StepOutcome' is deprecated, use 'StopOutcome'",
            DeprecationWarning,
            stacklevel=2,
        )
        return StopOutcome
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
