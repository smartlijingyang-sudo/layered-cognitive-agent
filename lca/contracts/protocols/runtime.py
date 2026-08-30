"""L2 Runtime 协议 —— 认知循环入口。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState, StateSnapshot
from lca.contracts.models.core.stop import StopDecision
from lca.contracts.models.team.run_context import RunContext


@runtime_checkable
class Runtime(Protocol):
    """认知循环入口：驱动 perceive → think → act → reflect 循环。"""

    async def run(
        self,
        task: str,
        ctx: RunContext | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        agent_role: str = "",
    ) -> Result: ...
    async def resume(
        self,
        snapshot: StateSnapshot,
        input: object | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> Result: ...


@runtime_checkable
class StopPolicy(Protocol):
    """Decide whether the fixed stop phase ends the current cognitive run.

    This is a State-cluster strategy. It is intentionally visible only through
    the stop phase's narrow capability view, rather than as a peer AgentGraph
    dependency or a top-level AgentSpec selection axis.
    """

    def decide(
        self,
        state: AgentState,
        decision: Decision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StopDecision: ...


# Backwards-compat aliases — C4 renamed both ``StopRule`` and ``StopOutcomePolicy``
# into the single ``StopPolicy`` (returns StopDecision). Downstream code on this
# branch (lca.contracts.__init__ re-exports) still references the old names.
# Restore as thin aliases so the tree imports until the protocol layer is
# fully migrated. Mirrors commit 945cc3ba (DECISION_GATE) / ecfc5031
# (StopOutcome) precedent.
StopRule = StopPolicy
StopOutcomePolicy = StopPolicy
