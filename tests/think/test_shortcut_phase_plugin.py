"""Tests for phase.think.shortcut plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.plugins.think.shortcut import ThinkShortcutExecutor


@dataclass
class _NoopShortcut:
    async def try_shortcut(self, state: AgentState) -> Decision | None:
        return None


@dataclass
class _HitShortcut:
    out: Decision

    async def try_shortcut(self, state: AgentState) -> Decision | None:
        return self.out


@dataclass
class _StubRuntime:
    state: AgentState | None
    supports_shortcut: Any


def _ctx(caps: dict[str, Any]) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    runtime = _StubRuntime(
        state=state,
        supports_shortcut=caps.get("phase.think.shortcut"),
    )
    return NodeContext(runtime=runtime, budget={}, metadata={})


@pytest.mark.asyncio
async def test_shortcut_hit_returns_decision_port() -> None:
    executor = ThinkShortcutExecutor()
    decision = Decision(
        decision_id="dec_x",
        action_type="respond",
        rationale="r",
        confidence=1.0,
    )
    output = await executor.node_execute(
        _ctx({"phase.think.shortcut": _HitShortcut(out=decision)}),
        NodeInput(port_values={}),
    )
    assert output.port_values == {"decision": decision}


@pytest.mark.asyncio
async def test_shortcut_miss_returns_empty_ports() -> None:
    executor = ThinkShortcutExecutor()
    output = await executor.node_execute(
        _ctx({"phase.think.shortcut": _NoopShortcut()}),
        NodeInput(port_values={}),
    )
    assert output.port_values == {}


@pytest.mark.asyncio
async def test_shortcut_missing_capability_returns_empty_ports() -> None:
    executor = ThinkShortcutExecutor()
    output = await executor.node_execute(_ctx({}), NodeInput(port_values={}))
    assert output.port_values == {}