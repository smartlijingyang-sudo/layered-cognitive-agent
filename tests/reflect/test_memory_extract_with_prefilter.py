# tests/reflect/test_memory_extract_with_prefilter.py
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.memory.filter import FilterDecision
from lca.nodes.reflect.memory_extract.memory_extract import ReflectMemoryExtractExecutor


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_t", task=task, budget=Budget())


def _reflection() -> Reflection:
    return Reflection(reflection_id="refl_1", verdict=ReflectionVerdict.ON_TRACK)


@pytest.mark.asyncio
async def test_executor_with_prefilter_blocked():
    mock_filter = AsyncMock()
    mock_filter.evaluate.return_value = FilterDecision(
        should_extract=False,
        reason="blocked_by_typesafe",
        source="typesafe",
        confidence=0.1,
    )
    mock_adapter = AsyncMock()

    executor = ReflectMemoryExtractExecutor(pre_filter=mock_filter)
    context = NodeContext(
        runtime={"adapter": mock_adapter, "agent_state": _state("你好，请帮我查天气")},
        metadata={},
        budget=None,
    )
    node_input = NodeInput(port_values={"reflection": _reflection()})

    output = await executor.node_execute(context, node_input)
    reflection = output.port_values["reflection"]

    # 阻断时不调用 adapter
    assert mock_adapter.complete.call_count == 0
    assert "memory_candidates" not in (getattr(reflection, "extra", {}) or {})
    assert mock_filter.evaluate.call_count == 1


@pytest.mark.asyncio
async def test_executor_with_prefilter_allowed_and_records_evidence():
    mock_filter = AsyncMock()
    mock_filter.evaluate.return_value = FilterDecision(
        should_extract=True,
        reason="noul_prob:0.92",
        source="typesafe",
        confidence=0.92,
    )
    mock_adapter = AsyncMock()
    mock_adapter.complete.return_value = LLMResponse(
        text='[{"category": "preference", "content": "用户偏好：回答简洁", "confidence": 1.0, "dedupe_key": "pref:concise"}]',
        model="stub",
    )

    executor = ReflectMemoryExtractExecutor(pre_filter=mock_filter)
    context = NodeContext(
        runtime={"adapter": mock_adapter, "agent_state": _state("回答尽量精炼，不要废话")},
        metadata={},
        budget=None,
    )
    node_input = NodeInput(port_values={"reflection": _reflection()})

    output = await executor.node_execute(context, node_input)
    reflection = output.port_values["reflection"]

    assert mock_adapter.complete.call_count == 1
    candidates = reflection.extra.get("memory_candidates")
    assert candidates is not None
    assert candidates[0]["content"] == "用户偏好：回答简洁"

    # 验证 C13 信息血统追踪指标
    pre_filter_meta = reflection.extra.get("pre_filter")
    assert pre_filter_meta is not None
    assert pre_filter_meta["source"] == "typesafe"
    assert pre_filter_meta["confidence"] == 0.92
