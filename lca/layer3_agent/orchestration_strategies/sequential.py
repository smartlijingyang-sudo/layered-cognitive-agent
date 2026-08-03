"""SequentialStrategy — CHOREOGRAPHY: A → B → C with output chaining."""

from __future__ import annotations

from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_members_sequential


class SequentialStrategy(TeamProcessStrategy):
    """Chain members in order; each member's output becomes the next task."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        return await invoke_members_sequential(
            context, objective, pass_output_as_next_task=True, stop_on_first_completed=False
        )
