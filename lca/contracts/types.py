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
    member_id: str
    objective: str
    depends_on: list[str] = field(default_factory=list)
