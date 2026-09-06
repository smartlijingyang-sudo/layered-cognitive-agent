"""Tool guard service — act-plane contribution registry (ADR-0197)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from lca.cognition.collaboration.group_assembly import OrderedContributionCatalog
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.act.tool.guards import ExecuteWrapper, ToolGuardContribution
from lca.contracts.protocols.act.tool.pipeline import ToolExecutionContext
from lca.contracts.protocols.runtime.infra.infra import Tool


class ToolGuardService:
    """Registry for act-plane guard plugins (timeout, spill, …)."""

    key = "tool_guards"

    def __init__(self) -> None:
        self._contributions = OrderedContributionCatalog[ToolGuardContribution](
            group="tool_guard", contribution_kind="guard"
        )

    def add(self, contribution: ToolGuardContribution, *, id: str, order: int = 0) -> None:
        self._contributions.register(id=id, order=order, value=contribution)

    def ordered(self) -> tuple[ToolGuardContribution, ...]:
        return tuple(entry.value for entry in self._contributions.ordered())

    async def execute_with_guards(
        self,
        tool: Tool,
        args: dict[str, object],
        inner: Callable[[], Awaitable[Observation]],
    ) -> Observation:
        async def terminal(_tool: Tool, _args: dict[str, object], run: Callable[[], Awaitable[Observation]]) -> Observation:
            return await run()

        chain: ExecuteWrapper = terminal
        for contribution in reversed(self.ordered()):
            chain = contribution.wrap_execute(chain)
        return await chain(tool, args, inner)

    async def apply_post_execute(
        self,
        ctx: ToolExecutionContext,
        observation: Observation,
    ) -> Observation:
        result = observation
        for contribution in self.ordered():
            result = contribution.transform_result(ctx, result)
        return result


__all__ = ["ToolGuardService"]
