"""PR-3（ADR-0246）：``phase.reflect.memory.extract`` 快速路径零 LLM 调用。"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.execution.decision import Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.reflect.memory_extract.memory_extract import ReflectMemoryExtractExecutor


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_t", task=task, budget=Budget())


def _reflection(**extra: object) -> Reflection:
    return Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra=extra,
    )


class _ExplodingAdapter:
    """若被调用则抛错：快速路径必须永不触达 adapter。"""

    async def complete(self, prompt: str, **kwargs: object) -> object:
        raise AssertionError("fast path must not call the LLM adapter")


@pytest.mark.asyncio
async def test_ordinary_reply_returns_unchanged_reflection() -> None:
    executor = ReflectMemoryExtractExecutor()
    reflection = _reflection()
    context = NodeContext(
        runtime={"adapter": _ExplodingAdapter(), "agent_state": _state("帮我查一下天气")},
        metadata={},
        budget=None,
    )
    output = await executor.node_execute(context, NodeInput(port_values={"reflection": reflection}))

    assert output.port_values["reflection"] is reflection
    assert reflection.extra == {}


@pytest.mark.asyncio
async def test_fast_path_flag_skips_extraction() -> None:
    executor = ReflectMemoryExtractExecutor()
    reflection = _reflection(fast_path=True)
    context = NodeContext(
        runtime={"adapter": _ExplodingAdapter(), "agent_state": _state("我是架构师")},
        metadata={},
        budget=None,
    )
    output = await executor.node_execute(context, NodeInput(port_values={"reflection": reflection}))

    assert output.port_values["reflection"] is reflection
    assert reflection.extra == {"fast_path": True}


@pytest.mark.asyncio
async def test_missing_reflection_returns_none() -> None:
    executor = ReflectMemoryExtractExecutor()
    context = NodeContext(runtime={"adapter": _ExplodingAdapter()}, metadata={}, budget=None)
    output = await executor.node_execute(context, NodeInput(port_values={"reflection": None}))

    assert output.port_values["reflection"] is None


@pytest.mark.asyncio
async def test_missing_adapter_is_fail_soft() -> None:
    executor = ReflectMemoryExtractExecutor()
    reflection = _reflection()
    context = NodeContext(runtime={"agent_state": _state("我是架构师")}, metadata={}, budget=None)
    output = await executor.node_execute(context, NodeInput(port_values={"reflection": reflection}))

    assert output.port_values["reflection"] is reflection
    assert "memory_candidates" not in reflection.extra


@pytest.mark.asyncio
async def test_adapter_error_is_fail_soft() -> None:
    class _BrokenAdapter:
        async def complete(self, prompt: str, **kwargs: object) -> object:
            raise RuntimeError("llm down")

    executor = ReflectMemoryExtractExecutor()
    reflection = _reflection()
    context = NodeContext(
        runtime={"adapter": _BrokenAdapter(), "agent_state": _state("我是架构师")},
        metadata={},
        budget=None,
    )
    output = await executor.node_execute(context, NodeInput(port_values={"reflection": reflection}))

    assert output.port_values["reflection"] is reflection
    assert "memory_candidates" not in reflection.extra
