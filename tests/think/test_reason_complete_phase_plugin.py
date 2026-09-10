"""Tests for phase.think.reason.complete plugin (ADR-0217 §3.3 + ADR-0218 §3.3).

think.reason inner_graph 第 3 节点 — ``await complete_turn`` 薄壳(唯一调 LLM)。

Case 矩阵(spec §3.1):
1. executor ``await reasoner.complete_turn`` 1 次
2. 上游 port 缺 ``turn_render`` 返回空
3. 注入 None reasoner 返回空
4. 不调任何 emit 函数(反向断言:模块级不 import emit)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.plugins.think.reason.complete import ThinkReasonCompleteExecutor


@dataclass
class _Reasoner:
    response: LLMResponse
    call_count: int = 0
    received_render: ReasonerTurnRender | None = None

    async def complete_turn(self, state: AgentState, render: ReasonerTurnRender) -> LLMResponse:
        self.call_count += 1
        self.received_render = render
        return self.response


@dataclass
class _StubRuntime:
    state: AgentState | None
    reasoner: Any


def _ctx(caps: dict[str, Any]) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    runtime = _StubRuntime(
        state=state,
        reasoner=caps.get("phase.think.reason.complete"),
    )
    return NodeContext(runtime=runtime, budget={}, metadata={})


def _render() -> ReasonerTurnRender:
    return ReasonerTurnRender(
        prompt="p",
        trace=None,
        section_count=0,
        manifest=None,
        activated_skill_ids=(),
        section_outputs=None,
        total_chars=None,
        variant=None,
    )


@pytest.mark.asyncio
async def test_reason_complete_attaches_response_port() -> None:
    """Executor ``await reasoner.complete_turn(state, render)`` 1 次,返回 response。"""
    executor = ThinkReasonCompleteExecutor()
    reasoner = _Reasoner(response=LLMResponse(text="hi", tool_calls=()))
    render = _render()
    result = await executor.node_execute(
        _ctx({"phase.think.reason.complete": reasoner}),
        NodeInput(port_values={"turn_render": render}),
    )
    assert reasoner.call_count == 1
    assert reasoner.received_render is render
    assert result.port_values.get("response") is reasoner.response


@pytest.mark.asyncio
async def test_reason_complete_missing_upstream_render_returns_empty_ports() -> None:
    """上游 port 缺 ``turn_render`` → 返回空 ports(铁律 2:缺失输入 = 空 NodeOutput)。"""
    executor = ThinkReasonCompleteExecutor()
    reasoner = _Reasoner(response=LLMResponse(text="hi", tool_calls=()))
    result = await executor.node_execute(
        _ctx({"phase.think.reason.complete": reasoner}),
        NodeInput(port_values={}),
    )
    assert reasoner.call_count == 0
    assert result.port_values == {}


@pytest.mark.asyncio
async def test_reason_complete_missing_capability_returns_empty_ports() -> None:
    """注入 None reasoner → 返回空 ports。"""
    executor = ThinkReasonCompleteExecutor()
    result = await executor.node_execute(
        _ctx({}),
        NodeInput(port_values={"turn_render": _render()}),
    )
    assert result.port_values == {}


def test_reason_complete_module_does_not_import_emit() -> None:
    """反向断言:模块级不 import emit(EP 由 driver 调度,executor 不知道 EP)。"""
    import lca.plugins.think.reason.complete as mod

    src = mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "from lca.infrastructure.session.emit" not in text
    assert "from lca.loop.emit" not in text
