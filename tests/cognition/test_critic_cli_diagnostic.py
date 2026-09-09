"""Critic defense-in-depth for CLI diagnostic stdout."""

from __future__ import annotations

import pytest

from lca.cognition.brain.reasoner.critic import SimpleCritic
from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState


@pytest.mark.asyncio
async def test_critic_rejects_diagnostic_stdout_even_when_success_true() -> None:
    state = AgentState(trace_id="t", task="poll", budget=create_budget(max_steps=8))
    observation = Observation(
        observation_id="o1",
        success=True,
        payload={
            "stdout": "'read' was not matched. Did you mean one of the following?\nraw\nUsage:\n  officecli",
        },
    )
    reflection = await SimpleCritic().critique(state, observation)
    assert reflection.verdict == ReflectionVerdict.NEEDS_CORRECTION
    assert reflection.extra.get(FAILURE_KIND) == FAILURE_KIND_VALIDATION
