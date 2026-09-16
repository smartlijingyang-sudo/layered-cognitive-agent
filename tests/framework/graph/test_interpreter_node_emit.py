"""Node-level ``emit_on_enter`` / ``emit_on_exit`` dispatch (ADR-0240).

The driver owns the dispatch so a declaration fires for every binding.
The regression this file pins: ``bundles/outer/phase_main.yaml`` declares
``emit_on_exit: [terminal.commit]`` on a node bound to ``terminate``, and
``NodeEventEmissionCheck`` *requires* terminal nodes to declare an exit
anchor. While the dispatch lived inside ``NodeExecutorStrategy`` the
``terminate`` binding resolved to ``TerminateStrategy`` instead, so
``spine.terminal.commit`` was never written — 0 occurrences across 578
run ledgers under ``traces/runs/``.

Tests patch :func:`emit_for_node` to record ids without standing up the
kernel; the concern under test is the wiring, not the helper bodies.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanNode
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lift.graph_spec import lift_graph_spec
from lca.framework.graph.strategy_registry import (
    NodeExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
)

_EMIT_SYMBOL = "lca.loop.emit.node_emitter.emit_for_node"


@dataclass(frozen=True, slots=True)
class _EchoExecutor:
    """Node executor that passes its input ports straight through."""

    semantic_name: str = "test.echo"
    declared_inputs: tuple[str, ...] = ()
    declared_outputs: tuple[str, ...] = ()

    async def node_execute(self, ctx: Any, input: Any) -> Any:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeOutput as LegacyNodeOutput,
        )

        return LegacyNodeOutput(port_values=dict(input.port_values))


@dataclass(frozen=True, slots=True)
class _RaisingExecutor:
    """Node executor whose body raises, to pin the failure path."""

    semantic_name: str = "test.raise"
    declared_inputs: tuple[str, ...] = ()
    declared_outputs: tuple[str, ...] = ()

    async def node_execute(self, ctx: Any, input: Any) -> Any:
        raise RuntimeError("simulated node body failure")


def _registry(executor: Any) -> StrategyRegistry:
    """Registry whose NODE_EXECUTOR binding resolves to ``executor``.

    Built from the production defaults so TERMINATE keeps resolving to
    the real ``TerminateStrategy`` — the binding under test.
    """
    lookup: NodeExecutorLookup = lambda *, binding, node_id, region: executor  # noqa: E731
    from lca.framework.graph.host_wiring import build_registry
    from lca.framework.graph.observation import NullGraphObserver

    return build_registry(
        lambda *a, **kw: None,
        lambda: 1,
        lookup,
        lambda state: {},
        NullGraphObserver(),
        lambda: 0,
        default_strategy_registry(),
    )


def _plan(node: PlanNode) -> Plan:
    return Plan(id="test.plan", nodes=(node.model_copy(update={"entry": True}),), edges=())


def _run(node: PlanNode, executor: Any) -> list[str]:
    """Interpret one node and return the EP ids the driver dispatched."""
    captured: list[str] = []

    def record(ep_id: str, state: Any, **kwargs: Any) -> None:
        captured.append(ep_id)

    registry = _registry(executor)
    if node.binding is BindingKind.TERMINATE:
        registry = default_strategy_registry()
    with patch(_EMIT_SYMBOL, side_effect=record):
        asyncio.run(
            PlanInterpreter(registry=registry).run(
                _plan(node), outer_state=None, port_registry_seed={}
            )
        )
    return captured


def _node(
    binding: BindingKind, config: Mapping[str, Any], *, outputs: tuple[str, ...] = ()
) -> PlanNode:
    schema = NodeIOSchema(
        outputs=tuple(PortSpec(name=name) for name in outputs),
    )
    return PlanNode(
        id="test.node",
        binding=binding,
        terminal=True,
        io_schema=schema,
        config=dict(config),
    )


def test_terminate_binding_fires_declared_emit_on_exit() -> None:
    """The regression: a ``terminate`` node's declared exit anchor fires."""
    captured = _run(
        _node(
            BindingKind.TERMINATE,
            {"config": {"emit_on_exit": ["terminal.commit"]}},
            outputs=("terminal_outcome",),
        ),
        executor=None,
    )
    assert captured == ["terminal.commit"]


def test_node_executor_binding_still_fires_declared_emits() -> None:
    """Moving the dispatch to the driver did not break the working binding."""
    captured = _run(
        _node(
            BindingKind.NODE_EXECUTOR,
            {
                "config": {
                    "emit_on_enter": ["phase.perceive.fold"],
                    "emit_on_exit": ["think.gate.end"],
                }
            },
        ),
        executor=_EchoExecutor(),
    )
    assert captured == ["phase.perceive.fold", "think.gate.end"]


def test_enter_fires_before_executor_and_exit_after() -> None:
    """Ordering is preserved: enter, body, exit."""
    order: list[str] = []

    class _OrderingExecutor:
        semantic_name = "test.order"
        declared_inputs: tuple[str, ...] = ()
        declared_outputs: tuple[str, ...] = ()

        async def node_execute(self, ctx: Any, input: Any) -> Any:
            from lca.contracts.protocols.declarative.declarative_1.node_executor import (
                NodeOutput as LegacyNodeOutput,
            )

            order.append("body")
            return LegacyNodeOutput(port_values={})

    def record(ep_id: str, state: Any, **kwargs: Any) -> None:
        order.append(ep_id)

    node = _node(
        BindingKind.NODE_EXECUTOR,
        {"config": {"emit_on_enter": ["enter.ep"], "emit_on_exit": ["exit.ep"]}},
    )
    with patch(_EMIT_SYMBOL, side_effect=record):
        asyncio.run(
            PlanInterpreter(registry=_registry(_OrderingExecutor())).run(
                _plan(node), outer_state=None, port_registry_seed={}
            )
        )
    assert order == ["enter.ep", "body", "exit.ep"]


def test_exit_emits_do_not_fire_when_the_node_raises() -> None:
    """A raising body exits via the failure observation, not via emit_on_exit."""
    node = _node(
        BindingKind.NODE_EXECUTOR,
        {"config": {"emit_on_enter": ["enter.ep"], "emit_on_exit": ["exit.ep"]}},
    )
    captured: list[str] = []
    with (
        patch(_EMIT_SYMBOL, side_effect=lambda ep, state, **kw: captured.append(ep)),
        pytest.raises(RuntimeError, match="simulated node body failure"),
    ):
        asyncio.run(
            PlanInterpreter(registry=_registry(_RaisingExecutor())).run(
                _plan(node), outer_state=None, port_registry_seed={}
            )
        )
    assert captured == ["enter.ep"]


def test_empty_and_absent_declarations_produce_zero_events() -> None:
    node_a = _node(
        BindingKind.TERMINATE,
        {"config": {"emit_on_enter": [], "emit_on_exit": []}},
        outputs=("terminal_outcome",),
    )
    node_b = _node(BindingKind.TERMINATE, {}, outputs=("terminal_outcome",))
    assert _run(node_a, executor=None) == []
    assert _run(node_b, executor=None) == []


def test_flat_config_shape_also_dispatches() -> None:
    """Hand-built plans declare ``config[key]`` without the yaml nesting."""
    captured = _run(
        _node(
            BindingKind.TERMINATE,
            {"emit_on_exit": ["terminal.commit"]},
            outputs=("terminal_outcome",),
        ),
        executor=None,
    )
    assert captured == ["terminal.commit"]


def test_multiple_emits_fire_in_declaration_order() -> None:
    captured = _run(
        _node(
            BindingKind.TERMINATE,
            {"config": {"emit_on_exit": ["phase.act.fold.end", "terminal.commit"]}},
            outputs=("terminal_outcome",),
        ),
        executor=None,
    )
    assert captured == ["phase.act.fold.end", "terminal.commit"]


def test_dispatcher_failure_is_contained() -> None:
    """An EP whose helper raises must not abort the graph (ADR-0240)."""
    node = _node(
        BindingKind.TERMINATE,
        {"config": {"emit_on_exit": ["terminal.commit"]}},
        outputs=("terminal_outcome",),
    )

    def explode(ep_id: str, state: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated handler failure")

    with patch(_EMIT_SYMBOL, side_effect=explode):
        result = asyncio.run(
            PlanInterpreter(registry=default_strategy_registry()).run(
                _plan(node), outer_state=None, port_registry_seed={}
            )
        )
    assert result.terminal_node == "test.node"


def test_production_outer_bundle_terminal_commit_declaration_fires() -> None:
    """The real ``phase_main.yaml`` anchor reaches the dispatcher.

    Lifts the production bundle and drives only its ``terminal.commit``
    node, so the assertion covers the yaml → lift → driver → dispatcher
    chain rather than a hand-built config shape.
    """
    repo_root = Path(__file__).resolve().parents[3]
    spec = yaml.safe_load((repo_root / "bundles/outer/phase_main.yaml").read_text(encoding="utf-8"))
    plan = lift_graph_spec(spec)
    node = next(n for n in plan.nodes if n.id == "terminal.commit")
    assert node.binding is BindingKind.TERMINATE
    assert node.terminal is True

    captured = _run(node, executor=None)
    assert captured == ["terminal.commit"]
