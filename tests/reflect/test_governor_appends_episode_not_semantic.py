"""ADR-0249: the governor appends an episode file and does not open semantic memory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.execution.decision import Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.memory.episode import EpisodeFact
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.reflect.memory_extract.memory_extract import ReflectMemoryExtractExecutor


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_t", task=task, budget=Budget())


def _reflection() -> Reflection:
    return Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={},
    )


class _ExplodingAdapter:
    """若被调用则抛错：governor 成功路径必须永不触达 adapter。"""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, prompt: str, **kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("governor path must not call the LLM adapter")


def _context(home: Path | None, task: str, adapter: object | None) -> NodeContext:
    runtime: dict[str, object] = {"agent_state": _state(task)}
    if home is not None:
        runtime["assistant_home_path"] = str(home)
    if adapter is not None:
        runtime["adapter"] = adapter
    return NodeContext(runtime=runtime, metadata={}, budget=None)


@pytest.mark.asyncio
async def test_governor_appends_episode_not_semantic(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    adapter = _ExplodingAdapter()
    executor = ReflectMemoryExtractExecutor(governor_enabled=True)
    reflection = _reflection()
    output = await executor.node_execute(
        _context(home, "我是架构师", adapter),
        NodeInput(port_values={"reflection": reflection}),
    )

    episodes = list((home / "memory" / "episodes").glob("*.json"))
    assert len(episodes) == 1
    fact = EpisodeFact.model_validate(json.loads(episodes[0].read_text(encoding="utf-8")))
    assert fact.content == "用户身份：架构师"
    assert output.port_values["reflection"] is reflection
    assert reflection.extra == {}
    assert adapter.calls == 0
    assert not (home / "memory" / "semantic.json").exists()


@pytest.mark.asyncio
async def test_low_residual_writes_no_episode(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    adapter = _ExplodingAdapter()
    executor = ReflectMemoryExtractExecutor(governor_enabled=True)
    reflection = _reflection()
    await executor.node_execute(
        _context(home, "帮我查一下天气", adapter),
        NodeInput(port_values={"reflection": reflection}),
    )

    assert not (home / "memory" / "episodes").exists()
    assert adapter.calls == 0
    assert reflection.extra == {}


@pytest.mark.asyncio
async def test_governor_disabled_is_fail_soft_without_episode_dir(tmp_path: Path) -> None:
    executor = ReflectMemoryExtractExecutor(governor_enabled=False)
    reflection = _reflection()
    episodes = Path.cwd() / "memory" / "episodes"
    existed = episodes.exists()
    output = await executor.node_execute(
        _context(None, "我是架构师", None),
        NodeInput(port_values={"reflection": reflection}),
    )

    assert output.port_values["reflection"] is reflection
    assert reflection.extra == {}
    assert "fast_path" not in reflection.extra
    if not existed:
        assert not episodes.exists()
    assert not (tmp_path / "memory" / "episodes").exists()
