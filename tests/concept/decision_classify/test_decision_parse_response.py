"""Tests for ADR-0221 — decision.parse.response merged parse node.

``concept.decision.classify`` 图节点 1 在 ADR-0221 合并 ``decision.parse.tool_calls`` +
``decision.parse.intent`` 后,单 pass 产出 ``tool_calls`` / ``delegations`` / ``intent`` 三端口。

回归目标:
1. happy path:tool_calls + intent 同时存在
2. only tool_calls:intent 为空字符串
3. only intent text:无 tool_calls
4. only delegate tool name:过滤到 delegations
5. leak recovery + intent 提取顺序:leaked JSON 不被重复提取进 intent
6. response 端口类型校验
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    NativeToolCall,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.plugins.concept.decision_classify.parse_tool_calls import (
    DecisionParseResponseExecutor,
)


def _ctx() -> NodeContext:
    return NodeContext(
        runtime={},
        budget={},
        metadata={"plan_ref": "concept.decision.classify", "node_id": "decision.parse.response"},
    )


def _input(response: LLMResponse | object) -> NodeInput:
    return NodeInput(port_values={"response": response})


async def _run(response: LLMResponse | object):
    executor = DecisionParseResponseExecutor()
    return await executor.node_execute(_ctx(), _input(response))


@pytest.mark.asyncio
async def test_happy_path_tool_calls_and_intent() -> None:
    response = LLMResponse(
        text="我先看下文件。",
        finish_reason="tool_calls",
        tool_calls=[
            NativeToolCall(call_id="c1", name="listFiles", arguments={"path": "/example"}),
        ],
    )
    out = await _run(response)
    tool_calls = out.port_values["tool_calls"]
    delegations = out.port_values["delegations"]
    intent = out.port_values["intent"]

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "listFiles"
    assert tool_calls[0].call_id == "c1"
    assert tool_calls[0].arguments == {"path": "/example"}
    assert len(delegations) == 0
    assert intent == "我先看下文件。"


@pytest.mark.asyncio
async def test_only_tool_calls_intent_empty() -> None:
    response = LLMResponse(
        text="",
        finish_reason="tool_calls",
        tool_calls=[
            NativeToolCall(call_id="c1", name="listFiles", arguments={}),
        ],
    )
    out = await _run(response)
    assert len(out.port_values["tool_calls"]) == 1
    assert out.port_values["delegations"] == ()
    assert out.port_values["intent"] == ""


@pytest.mark.asyncio
async def test_only_intent_no_tool_calls() -> None:
    response = LLMResponse(text="你好,有什么可以帮你?", finish_reason="stop")
    out = await _run(response)
    assert out.port_values["tool_calls"] == ()
    assert out.port_values["delegations"] == ()
    assert out.port_values["intent"] == "你好,有什么可以帮你?"


@pytest.mark.asyncio
async def test_delegate_tool_filtered_to_delegations() -> None:
    response = LLMResponse(
        text="",
        finish_reason="tool_calls",
        tool_calls=[
            NativeToolCall(
                call_id="c1",
                name="delegate",
                arguments={"subtask": "子任务", "target_role": "researcher"},
            ),
        ],
    )
    out = await _run(response)
    assert out.port_values["tool_calls"] == ()
    assert len(out.port_values["delegations"]) == 1
    spec = out.port_values["delegations"][0]
    assert spec.subtask == "子任务"
    assert spec.target_role == "researcher"


@pytest.mark.asyncio
async def test_leak_recovery_then_intent_does_not_double_count() -> None:
    """leaked JSON 必须先于 intent 提取,否则 leaked JSON 会污染 intent 文本。

    这是 ADR-0221 合并节点的关键回归点 —— 原 3 节点图下 leak recovery 在
    ``decision.parse.tool_calls`` 节点,``intent`` 在 ``decision.parse.intent`` 节点,
    两者独立读 ``response.text``。合并后必须保证:
    1. leak recovery 修改 ``leftover``(剥离 leaked JSON)
    2. intent 计算用剥离后的 ``leftover``,而不是原始 ``response.text``
    """
    response = LLMResponse(
        text='我帮你看一下。\n[Tool call: listFiles]\n{"path": "/example"}',
        finish_reason="tool_calls",
        tool_calls=[],
    )
    out = await _run(response)
    assert len(out.port_values["tool_calls"]) == 1
    assert out.port_values["tool_calls"][0].tool_name == "listFiles"
    assert out.port_values["tool_calls"][0].arguments == {"path": "/example"}
    # intent 不应包含 leaked JSON
    assert "[Tool call:" not in out.port_values["intent"]
    assert "listFiles" not in out.port_values["intent"]
    assert out.port_values["intent"] == "我帮你看一下。"


@pytest.mark.asyncio
async def test_response_port_type_enforced() -> None:
    with pytest.raises(TypeError, match="must be an LLMResponse"):
        await _run("not an LLMResponse")


@pytest.mark.asyncio
async def test_executor_metadata_unchanged() -> None:
    executor = DecisionParseResponseExecutor()
    assert executor.semantic_name == "decision.parse.response"
    assert executor.region == "concept"
    assert executor.declared_inputs == ("response",)
    assert set(executor.declared_outputs) == {"tool_calls", "delegations", "intent"}
