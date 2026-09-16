"""L2 Runtime 协议 —— 认知循环入口。

The retired `StopPolicy` Protocol previously lived here; loop termination
now flows through the outer plan's `terminal.commit` node (`TerminateStrategy`)
reached by edge predicates over `decision.action_type`,
`act.observe.terminate_decide`'s `should_terminate`, and the budget guard.
See plan `docs/plans/2026-09-14-stop-decision-retirement.md` and
`docs/specs/tool-failure-recovery.md` §7.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.policy.budget import DEFAULT_MAX_STEPS
from lca.contracts.models.core.state.state import StateSnapshot
from lca.contracts.models.team.run.context import RunContext


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
