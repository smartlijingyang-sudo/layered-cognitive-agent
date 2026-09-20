"""ADR-0247 回归：无第一人称代词的偏好/纠正句也应触发记忆蒸馏。

流程测试发现：``_may_contain_self_reference`` 只查「我」等代词，导致
「还是简洁一点好」走零成本快速路径，偏好纠正未落盘、未 supersede。
本测试锁定成本门能识别无代词偏好句。
"""

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


class _RecordingAdapter:
    """记录被调用的 LLM adapter；返回空候选数组。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, prompt: str, **kwargs: object) -> object:
        self.calls.append(prompt)
        return type("_Response", (), {"text": "[]"})()


def _reflection() -> Reflection:
    return Reflection(reflection_id="refl_1", verdict=ReflectionVerdict.ON_TRACK)


def _context(task: str, adapter: object) -> NodeContext:
    return NodeContext(
        runtime={
            "adapter": adapter,
            "agent_state": AgentState(trace_id="trace_t", task=task, budget=Budget()),
        },
        metadata={},
        budget=None,
    )


@pytest.mark.asyncio
async def test_preference_correction_without_pronoun_triggers_extraction() -> None:
    executor = ReflectMemoryExtractExecutor()
    adapter = _RecordingAdapter()
    reflection = _reflection()

    await executor.node_execute(
        _context("还是简洁一点好", adapter),
        NodeInput(port_values={"reflection": reflection}),
    )

    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_ordinary_reply_still_uses_fast_path() -> None:
    executor = ReflectMemoryExtractExecutor()

    class _ExplodingAdapter:
        async def complete(self, prompt: str, **kwargs: object) -> object:
            raise AssertionError("fast path must not call the LLM adapter")

    reflection = _reflection()
    await executor.node_execute(
        _context("帮我查一下天气", _ExplodingAdapter()),
        NodeInput(port_values={"reflection": reflection}),
    )

    assert reflection.extra == {}
