"""Perceive records a closed-template episode before any tool turn."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.memory.episode import EpisodeFact
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.perceive.observe.observe import PerceiveObserveExecutor


class _Hub:
    def __init__(self) -> None:
        self.calls = 0

    async def perceive(self, state: object) -> ContextManifest:
        del state
        self.calls += 1
        return ContextManifest(items=())


class _Memory:
    def __init__(self, home: Path) -> None:
        self.home_path = home


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_perceive", task=task, budget=Budget())


@pytest.mark.asyncio
async def test_observe_appends_identity_episode_and_still_perceives(tmp_path: Path) -> None:
    hub = _Hub()
    home = tmp_path / "asst"
    executor = PerceiveObserveExecutor()
    output = await executor.node_execute(
        NodeContext(
            runtime={
                "perceive_hub": hub,
                "memory": _Memory(home),
                "agent_state": _state("我是架构师"),
            },
            metadata={},
            budget=None,
        ),
        NodeInput(port_values={}),
    )

    episodes = list((home / "memory" / "episodes").glob("*.json"))
    assert len(episodes) == 1
    fact = EpisodeFact.model_validate_json(episodes[0].read_text(encoding="utf-8"))
    assert fact.content == "用户身份：架构师"
    assert output.port_values["manifest"] == ContextManifest(items=())
    assert hub.calls == 1


@pytest.mark.asyncio
async def test_observe_skips_episode_when_the_utterance_has_no_template(tmp_path: Path) -> None:
    hub = _Hub()
    home = tmp_path / "asst"
    executor = PerceiveObserveExecutor()
    await executor.node_execute(
        NodeContext(
            runtime={
                "perceive_hub": hub,
                "memory": _Memory(home),
                "agent_state": _state("帮我查一下天气"),
            },
            metadata={},
            budget=None,
        ),
        NodeInput(port_values={}),
    )

    assert not (home / "memory" / "episodes").exists()
    assert hub.calls == 1
