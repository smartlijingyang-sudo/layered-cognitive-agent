"""Tests for phase.think.route plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
)
from lca.plugins.think.route.plugin import ThinkRouteExecutor


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
class _StubPhaseContext:
    plan_ref: str
    node_ref: str
    state: AgentState
    journal: Any
    budget: Any
    artifacts: dict[str, Any]
    capabilities: Any
    decision: Any
    observation: Any
    reflection: Any
    checkpoint_reason: Any

    def emit_fact(self, fact: Any) -> str:
        return ""

    def propose_delta(self, delta: Any) -> None:
        return None


def _ctx(caps: dict[str, Any]) -> _StubPhaseContext:
    return _StubPhaseContext(
        plan_ref="p",
        node_ref="think.route",
        state=AgentState(trace_id="t", task="x", budget=Budget()),
        journal=None,
        budget=None,
        artifacts={},
        capabilities=caps,
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_route_calls_reducer_with_router_template() -> None:
    executor = ThinkRouteExecutor()
    router = _Router(template="hierarchical_prompt")
    reducer = _Reducer()
    result = await executor.execute(
        _ctx(
            {
                "phase.think.route": router,
                "phase.think.reducer": reducer,
            }
        ),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)
    assert reducer.last_template == "hierarchical_prompt"


@pytest.mark.asyncio
async def test_route_without_router_passes_through() -> None:
    executor = ThinkRouteExecutor()
    result = await executor.execute(
        _ctx({"phase.think.reducer": _Reducer()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)


@pytest.mark.asyncio
async def test_route_with_router_but_no_reducer_raises() -> None:
    executor = ThinkRouteExecutor()
    with pytest.raises(RuntimeError, match=r"phase\.think\.reducer"):
        await executor.execute(
            _ctx({"phase.think.route": _Router()}),
            PhaseInput(artifact=None),
        )


@pytest.mark.asyncio
async def test_route_with_none_template_folds_to_state() -> None:
    """SkillRouter.route may return None; Reducer still gets called."""
    executor = ThinkRouteExecutor()
    reducer = _Reducer()
    await executor.execute(
        _ctx(
            {
                "phase.think.route": _Router(template=None),
                "phase.think.reducer": reducer,
            }
        ),
        PhaseInput(artifact=None),
    )
    assert reducer.last_template is None
