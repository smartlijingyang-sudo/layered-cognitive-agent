"""Tests for phase.think.route plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.plugins.think.route import ThinkRouteExecutor


@dataclass
class _Router:
    template: str | None = "react_prompt"

    async def route(self, state: AgentState) -> str | None:
        return self.template


@dataclass
class _Reducer:
    """Provides only ``apply_skill_route`` — the only method the route plugin uses."""

    last_template: str | None = None

    def apply_skill_route(self, state: AgentState, active_template: str | None) -> AgentState:
        self.last_template = active_template
        return state


@dataclass
class _StubRuntime:
    state: AgentState | None
    skill_router: Any
    reducer: Any


def _ctx(caps: dict[str, Any]) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    runtime = _StubRuntime(
        state=state,
        skill_router=caps.get("phase.think.route"),
        reducer=caps.get("phase.think.reducer"),
    )
    return NodeContext(runtime=runtime, budget={}, metadata={})


@pytest.mark.asyncio
async def test_route_calls_reducer_with_router_template() -> None:
    executor = ThinkRouteExecutor()
    router = _Router(template="hierarchical_prompt")
    reducer = _Reducer()
    output = await executor.node_execute(
        _ctx(
            {
                "phase.think.route": router,
                "phase.think.reducer": reducer,
            }
        ),
        NodeInput(port_values={}),
    )
    assert reducer.last_template == "hierarchical_prompt"
    assert output.port_values.get("route_choice") == "hierarchical_prompt"


@pytest.mark.asyncio
async def test_route_without_router_returns_empty_ports() -> None:
    executor = ThinkRouteExecutor()
    output = await executor.node_execute(
        _ctx({"phase.think.reducer": _Reducer()}),
        NodeInput(port_values={}),
    )
    assert output.port_values == {}


@pytest.mark.asyncio
async def test_route_with_router_but_no_reducer_raises() -> None:
    executor = ThinkRouteExecutor()
    with pytest.raises(RuntimeError, match=r"phase\.think\.reducer|reducer"):
        await executor.node_execute(
            _ctx({"phase.think.route": _Router()}),
            NodeInput(port_values={}),
        )


@pytest.mark.asyncio
async def test_route_with_none_template_folds_to_state() -> None:
    """SkillRouter.route may return None; Reducer still gets called."""
    executor = ThinkRouteExecutor()
    reducer = _Reducer()
    await executor.node_execute(
        _ctx(
            {
                "phase.think.route": _Router(template=None),
                "phase.think.reducer": reducer,
            }
        ),
        NodeInput(port_values={}),
    )
    assert reducer.last_template is None