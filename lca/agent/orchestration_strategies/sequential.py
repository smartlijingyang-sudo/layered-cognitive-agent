"""SequentialStrategy — CHOREOGRAPHY: A → B → C with output chaining."""

from __future__ import annotations

from lca.agent.member_invoke import invoke_members_sequential
from lca.contracts.models.core.result import Result
from lca.contracts.protocols import TeamStage, TeamStrategy


class SequentialStrategy(TeamStrategy):
    """Chain members in order; each member's output becomes the next task."""

    def __init__(self, stage: TeamStage) -> None:
        self._stage = stage

    async def run(self, objective: str) -> Result:
        return await invoke_members_sequential(
            self._stage, objective, pass_output_as_next_task=True, stop_on_first_completed=False
        )
