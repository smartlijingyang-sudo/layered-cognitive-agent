"""NullCritic —— ADR-0068 / 宪法 §3.4 默认 no-op。"""

import pytest

from lca.contracts.atoms.enums import ReflectionVerdict
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.state import AgentState
from lca.layer1_cognitive.brain.null_critic import NullCritic


@pytest.fixture()
def state() -> AgentState:
    return AgentState(trace_id="test-trace", task="test", budget=None)


def _obs(**kwargs) -> Observation:
    return Observation(observation_id=new_id("obs"), **kwargs)


@pytest.mark.asyncio
async def test_null_critic_returns_on_track(state: AgentState) -> None:
    critic = NullCritic()
    observation = _obs(success=True, payload="stub", extra={})
    reflection = await critic.critique(state, observation)
    assert reflection.verdict == ReflectionVerdict.ON_TRACK
    assert reflection.lesson is None


@pytest.mark.asyncio
async def test_null_critic_ignores_observation(state: AgentState) -> None:
    """NullCritic 不读 observation，永远返回 ON_TRACK / lesson=None。"""
    critic = NullCritic()
    obs1 = _obs(success=True, payload="good", extra={})
    obs2 = _obs(success=False, payload="bad", extra={})
    r1 = await critic.critique(state, obs1)
    r2 = await critic.critique(state, obs2)
    assert r1.verdict == r2.verdict == ReflectionVerdict.ON_TRACK
    assert r1.lesson == r2.lesson is None
