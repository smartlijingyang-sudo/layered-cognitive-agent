"""HierarchicalStrategy — supervisor delegates and synthesizes."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.contracts.run_context import RunContext


class HierarchicalStrategy(TeamProcessStrategy):
    """Supervisor-only path; member_status carried via RunContext."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        ctx = RunContext(member_status=context.member_status)
        for name in ("run", "execute"):
            fn = getattr(context.supervisor, name, None)
            if not callable(fn):
                continue
            if name == "run":
                out = fn(objective, ctx)
            else:
                out = fn(objective, member_status=context.member_status)
            if isinstance(out, Awaitable):
                return cast("Result", await out)
        return Result.failed("supervisor has no run method")
