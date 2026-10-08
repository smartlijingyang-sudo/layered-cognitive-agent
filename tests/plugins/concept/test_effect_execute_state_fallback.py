"""Regression: ``effect.execute`` must recover ``state`` when the typed port is unwired.

Root cause (todo-80): RA-033 removed the ``envelope.metadata`` smuggle path
for ``state`` / ``decision``, but the act subgraph never wired a ``state``
producer upstream of ``effect.execute`` — the outer ``think.main->act.main``
edge carries only ``decision``. On real runs the ``state`` typed port arrives
as ``None`` and ``BodyActEffectHandler`` raises PG-003, failing every
``body.act`` dispatch.

The node now falls back to the kernel-injected runtime port
(``context.runtime.state``) when the typed port is ``None`` — the same source
``_append_tool_result_surface`` already reads. Only a real ``AgentState`` is
accepted, so legacy fixtures keep the previous ``None`` (fail-loud) path.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.act.command.envelope import (
    CapabilityGrant,
    CommandEnvelope,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.concept.effect.execute import EffectExecuteExecutor


class _RecordingGateway:
    """Effect gateway seam recording the kwargs it was called with."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(self, envelope: Any, policy: Any, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return {"result": None, "invocation_id": "inv"}


class _Runtime:
    """Duck-typed ``_NodeRuntimeView`` exposing only what the node reads."""

    def __init__(self, *, gateway: Any, state: Any) -> None:
        self.writer = None
        self.effect_gateway = gateway
        self.state = state

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _envelope() -> CommandEnvelope:
    return CommandEnvelope(
        plan_ref="plan_v1",
        decision_ref="dec_1",
        provider="test-provider",
        grant=CapabilityGrant(capability="body.act", scope="run", effect_class="body.act"),
        idempotency_key="test-inv-key",
        metadata={"operation": "body.act", "effect_class": "body.act"},
    )


def _ctx(gateway: Any, state: Any) -> NodeContext:
    return NodeContext(
        runtime=_Runtime(gateway=gateway, state=state),
        budget={},
        metadata={"plan_ref": "act.subgraph", "node_id": "effect.execute"},
    )


def _state() -> AgentState:
    return AgentState(trace_id="trace_t", task="t", budget=Budget())


@pytest.mark.asyncio
async def test_state_port_none_falls_back_to_runtime_state() -> None:
    """The todo-80 wiring gap: port is None, runtime carries the real state."""
    gateway = _RecordingGateway()
    runtime_state = _state()

    await EffectExecuteExecutor().node_execute(
        _ctx(gateway, runtime_state),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    assert gateway.calls, "gateway must have been invoked"
    assert gateway.calls[0]["state"] is runtime_state


@pytest.mark.asyncio
async def test_no_runtime_state_keeps_previous_none() -> None:
    """Legacy fixtures without a runtime state keep the fail-loud path."""
    gateway = _RecordingGateway()

    await EffectExecuteExecutor().node_execute(
        _ctx(gateway, None),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    assert gateway.calls, "gateway must have been invoked"
    assert gateway.calls[0]["state"] is None


@pytest.mark.asyncio
async def test_typed_port_state_takes_precedence_over_runtime() -> None:
    """A wired typed port wins; the fallback never shadows it."""
    gateway = _RecordingGateway()
    port_state = _state()
    runtime_state = _state()

    await EffectExecuteExecutor().node_execute(
        _ctx(gateway, runtime_state),
        NodeInput(port_values={"envelope": _envelope(), "state": port_state}),
    )

    assert gateway.calls, "gateway must have been invoked"
    assert gateway.calls[0]["state"] is port_state
