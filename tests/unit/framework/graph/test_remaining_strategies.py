"""Tests for the PR-5 additional strategies.

Covers :class:`TransformStrategy`, :class:`ObserveStrategy`,
:class:`TerminateStrategy`, :class:`ParallelStrategy`,
:class:`GateChainStrategy`. Each test stubs the host-injected closure
so the strategies are exercised end-to-end.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeInput, NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph.strategies import (
    GateChainStrategy,
    ObserveStrategy,
    ParallelStrategy,
    TerminateStrategy,
    TransformStrategy,
)
from lca.framework.graph.strategies.parallel_strategy import _default_reducer


def _ctx(node_id: str = "x") -> StrategyContext:
    return StrategyContext(
        plan_ref="p",
        node_id=node_id,
        binding_kind=BindingKind.TRANSFORM,
        node_config={},
    )


class TestTransform:
    async def test_transform_runs_and_emits(self) -> None:
        def fn(values: dict[str, Any], ctx: StrategyContext) -> dict[str, Any]:
            return {"response": f"got {values.get('decision')}"}

        strategy = TransformStrategy(transform=fn)
        out = await strategy.execute(
            _ctx(), NodeInput(port_values={"decision": "a"})
        )
        assert out.port_values == {"response": "got a"}

    async def test_transform_requires_fn(self) -> None:
        strategy = TransformStrategy()
        with pytest.raises(RuntimeError, match="without transform"):
            await strategy.execute(_ctx(), NodeInput())

    async def test_identity_transform_preserves_inputs(self) -> None:
        strategy = TransformStrategy(transform=lambda v, c: dict(v))
        out = await strategy.execute(_ctx(), NodeInput(port_values={"decision": 1, "response": 2}))
        assert out.port_values == {"decision": 1, "response": 2}


class TestObserve:
    async def test_observer_called_with_ports(self) -> None:
        seen: list[dict[str, Any]] = []

        def observer(ctx: StrategyContext, ins: dict[str, Any], outs: dict[str, Any]) -> None:
            seen.append({"node_id": ctx.node_id, "in": dict(ins), "out": dict(outs)})

        strategy = ObserveStrategy(observer=observer)
        out = await strategy.execute(_ctx("n1"), NodeInput(port_values={"decision": 1}))
        assert out.port_values == {"decision": 1}
        assert seen[0]["node_id"] == "n1"

    async def test_observer_failure_does_not_break_execute(self) -> None:
        def bad(ctx: StrategyContext, ins: dict[str, Any], outs: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        strategy = ObserveStrategy(observer=bad)
        out = await strategy.execute(_ctx(), NodeInput(port_values={"decision": 1}))
        assert out.port_values == {"decision": 1}

    async def test_observer_failure_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Contained, not silent: the visit survives and the error is traceable."""

        def bad(ctx: StrategyContext, ins: dict[str, Any], outs: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        strategy = ObserveStrategy(observer=bad)
        logger = "lca.framework.graph.strategies.observe_strategy"
        with caplog.at_level(logging.ERROR, logger=logger):
            await strategy.execute(_ctx("obs-node"), NodeInput(port_values={"decision": 1}))

        messages = [r.getMessage() for r in caplog.records]
        assert any("obs-node" in m for m in messages), messages
        assert any("boom" in (r.exc_text or "") for r in caplog.records), messages


class TestTerminate:
    async def test_terminate_emits_payload(self) -> None:
        def fn(values: dict[str, Any], ctx: StrategyContext) -> dict[str, Any]:
            return {"response": f"end:{ctx.node_id}"}

        strategy = TerminateStrategy(terminate=fn)
        out = await strategy.execute(_ctx("n2"), NodeInput(port_values={"decision": "d"}))
        assert out.port_values == {"response": "end:n2"}

    async def test_terminate_falls_back_to_default_when_fn_missing(self) -> None:
        """Empty terminate fn → default terminator builds a StopPayload."""
        from lca.contracts.models.cognition.boundary import StopPayload

        strategy = TerminateStrategy()
        out = await strategy.execute(
            _ctx("n3"), NodeInput(port_values={"decision": "d"})
        )
        assert "terminal_outcome" in out.port_values
        assert isinstance(out.port_values["terminal_outcome"], StopPayload)

    async def test_terminate_uses_schema_declared_port_names(self) -> None:
        """Host-declared ``io_schema`` overrides the framework fallback."""
        from lca.contracts.models.cognition.boundary import StopPayload

        schema = NodeIOSchema(
            inputs=(
                PortSpec(name="my_decision"),
                PortSpec(name="my_act_outcome"),
            ),
            outputs=(PortSpec(name="my_terminal_outcome"),),
        )
        strategy = TerminateStrategy(schema=schema)
        out = await strategy.execute(
            _ctx("n4"),
            NodeInput(port_values={"my_decision": "d", "my_act_outcome": None}),
        )
        assert "my_terminal_outcome" in out.port_values
        assert "terminal_outcome" not in out.port_values
        assert isinstance(out.port_values["my_terminal_outcome"], StopPayload)


class TestParallel:
    async def test_runs_children_and_reduces(self) -> None:
        def child_runner(ref: str, port_values: dict[str, Any]) -> dict[str, Any]:
            return {"observation": f"{ref}:{port_values.get('decision')}"}

        strategy = ParallelStrategy(child_runner=child_runner, reducer=_default_reducer)
        ctx = StrategyContext(
            plan_ref="p",
            node_id="fork",
            binding_kind=BindingKind.PARALLEL,
            node_config={"children": ["a.yaml", "b.yaml"]},
        )
        out = await strategy.execute(ctx, NodeInput(port_values={"decision": "x"}))
        assert "observation" in out.port_values

    async def test_missing_children_raises(self) -> None:
        strategy = ParallelStrategy(child_runner=lambda *_: {}, reducer=_default_reducer)
        # _ctx() has no 'children' in node_config -> runtime error.
        with pytest.raises(RuntimeError, match="non-empty sequence"):
            await strategy.execute(_ctx(), NodeInput(port_values={"decision": "x"}))

    async def test_requires_child_runner(self) -> None:
        strategy = ParallelStrategy(reducer=_default_reducer)
        ctx = StrategyContext(
            plan_ref="p",
            node_id="fork",
            binding_kind=BindingKind.PARALLEL,
            node_config={"children": ["a.yaml"]},
        )
        with pytest.raises(RuntimeError, match="child_runner"):
            await strategy.execute(ctx, NodeInput(port_values={"decision": "x"}))


class TestGateChain:
    async def test_runs_gates_in_order(self) -> None:
        decisions: list[Any] = []

        def make_decision(decision_id: str) -> Any:
            class _D:
                pass

            d = _D()
            d.decision_id = decision_id
            return d

        class _StubGate:
            def __init__(self, suffix: str) -> None:
                self.suffix = suffix

            async def enforce(self, decision: Any) -> Any:
                decisions.append(decision)
                return make_decision(f"{decision.decision_id}-{self.suffix}")

        gates = [_StubGate("a"), _StubGate("b")]
        strategy = GateChainStrategy(gates=gates)
        starting = make_decision("d0")
        out = await strategy.execute(_ctx(), NodeInput(port_values={"decision": starting}))
        assert out.port_values["decision"].decision_id == "d0-a-b"
        assert len(decisions) == 2

    async def test_rejects_non_decision_input(self) -> None:
        strategy = GateChainStrategy(gates=())
        with pytest.raises(RuntimeError, match="decision-like"):
            await strategy.execute(_ctx(), NodeInput(port_values={"decision": "string"}))

    async def test_uses_schema_declared_port_names(self) -> None:
        """Host-declared ``io_schema`` overrides the framework fallback."""

        def make_decision(decision_id: str) -> Any:
            class _D:
                pass

            d = _D()
            d.decision_id = decision_id
            return d

        class _PassGate:
            async def enforce(self, decision: Any) -> Any:
                return decision

        schema = NodeIOSchema(
            inputs=(PortSpec(name="my_decision"),),
            outputs=(PortSpec(name="my_decision_out"),),
        )
        strategy = GateChainStrategy(gates=[_PassGate()], schema=schema)
        out = await strategy.execute(
            _ctx(), NodeInput(port_values={"my_decision": make_decision("d0")})
        )
        assert "my_decision_out" in out.port_values
        assert "decision" not in out.port_values


class TestStrategyRegistryExtras:
    """Smoke test that all 5 new strategies register at import time."""

    def test_all_registered(self) -> None:
        from lca.framework.graph import default_strategy_registry

        kinds = {k.value for k in default_strategy_registry().kinds()}
        assert {"transform", "observe", "terminate", "parallel", "gate_chain"}.issubset(kinds)
