"""PR-3（ADR-0246）：``phase.reflect.memory.extract`` LLM 蒸馏身份/偏好候选。

验证中文自然陈述（无关键词）产出结构化候选、普通回复零 LLM 调用。
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.reflect.memory_extract.memory_extract import (
    ReflectMemoryExtractExecutor,
    _may_contain_self_reference,
    _parse_candidates,
)


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_t", task=task, budget=Budget())


def _reflection() -> Reflection:
    return Reflection(reflection_id="refl_1", verdict=ReflectionVerdict.ON_TRACK)


class _JsonLLMAdapter:
    """Stub adapter：返回固定 JSON 文本。"""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self._text, model="stub")


def test_may_contain_self_reference_gate() -> None:
    assert _may_contain_self_reference("我是架构师")
    assert _may_contain_self_reference("我不喜欢啰嗦")
    assert _may_contain_self_reference("I am an architect")
    assert _may_contain_self_reference("please remember my name is Bob")
    assert not _may_contain_self_reference("什么是快手电商？")
    assert not _may_contain_self_reference("好的，谢谢")
    assert not _may_contain_self_reference("")


def test_parse_candidates_extracts_structured_list() -> None:
    text = (
        '[{"category": "identity", "content": "用户身份：架构师", '
        '"confidence": 1.0, "dedupe_key": "identity:architect"}, '
        '{"category": "preference", "content": "用户偏好：不喜欢啰嗦", '
        '"confidence": 1.0, "dedupe_key": "preference:concise"}]'
    )
    candidates = _parse_candidates(text)
    assert len(candidates) == 2
    assert candidates[0]["category"] == "identity"
    assert candidates[1]["category"] == "preference"
    assert candidates[0]["content"] == "用户身份：架构师"


def test_parse_candidates_rejects_invalid_or_returns_empty() -> None:
    assert _parse_candidates("") == []
    assert _parse_candidates("not json") == []
    assert _parse_candidates('[{"category": "bogus", "content": "x"}]') == []
    assert _parse_candidates('[{"category": "identity", "content": ""}]') == []


@pytest.mark.asyncio
async def test_extract_distills_identity_without_keywords() -> None:
    adapter = _JsonLLMAdapter(
        '[{"category": "identity", "content": "用户身份：架构师", '
        '"confidence": 1.0, "dedupe_key": "identity:architect"}]'
    )
    executor = ReflectMemoryExtractExecutor()
    context = NodeContext(
        runtime={"adapter": adapter, "agent_state": _state("我是架构师")},
        metadata={},
        budget=None,
    )
    node_input = NodeInput(port_values={"reflection": _reflection()})

    output = await executor.node_execute(context, node_input)

    reflection = output.port_values["reflection"]
    candidates = reflection.extra.get("memory_candidates")
    assert candidates is not None
    assert candidates[0]["category"] == "identity"
    assert candidates[0]["content"] == "用户身份：架构师"
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_extract_does_not_call_llm_on_ordinary_reply() -> None:
    adapter = _JsonLLMAdapter("[]")
    executor = ReflectMemoryExtractExecutor()
    context = NodeContext(
        runtime={"adapter": adapter, "agent_state": _state("好的，谢谢")},
        metadata={},
        budget=None,
    )
    reflection = _reflection()
    node_input = NodeInput(port_values={"reflection": reflection})

    output = await executor.node_execute(context, node_input)

    assert output.port_values["reflection"] is reflection
    assert "memory_candidates" not in reflection.extra
    assert adapter.calls == 0
