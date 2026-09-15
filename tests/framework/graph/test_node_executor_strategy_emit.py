"""Tests for node-level emit dispatch in ``NodeExecutorStrategy``.

ADR-0240 / Note `2026-09-15-node-emit-dispatcher-wiring` cover the wiring:
the strategy reads ``emit_on_enter`` / ``emit_on_exit`` from
``context.node_config["config"][...]`` and forwards each entry to
:func:`emit_for_node`. These tests defend the four behaviors that matter:

- a non-empty ``emit_on_exit`` produces one EP per entry after dispatch;
- an empty list produces zero events;
- dispatcher failures are contained (do not propagate);
- nested ``config.config[key]`` and legacy flat ``config[key]`` both work.

They monkeypatch :func:`emit_for_node` to record calls without standing
up the full kernel — the integration concern is the wiring shape, not
the helper bodies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch


from lca.contracts.protocols.graph.node_io import (
    NodeInput,
)
from lca.framework.graph.strategies.node_executor_strategy import (
    NodeExecutorStrategy,
)
from lca.contracts.protocols.graph.binding import BindingKind


@dataclass(frozen=True, slots=True)
class _FakeNodeExecutor:
    """Stand-in for a real :class:`NodeExecutor`."""

    semantic_name: str = "test.executor"
    declared_inputs: tuple = ()
    declared_outputs: tuple = ()

    async def node_execute(self, ctx: Any, input: Any) -> Any:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeOutput as LegacyNodeOutput,
        )

        return LegacyNodeOutput(port_values=dict(input.port_values))


@dataclass(frozen=True, slots=True)
class _FakeContext:
    plan_ref: str = "test.plan"
    node_id: str = "commit"
    binding_kind: BindingKind = BindingKind.NODE_EXECUTOR
    chain: tuple = ()
    node_config: dict = field(default_factory=dict)


def _executor_lookup() -> dict:
    return {("NODE_EXECUTOR", "commit"): _FakeNodeExecutor()}


def _run_emit(node_config: dict) -> list[str]:
    """Dispatch one fake node through the strategy, capture emit_for_node calls."""
    import asyncio

    captured: list[str] = []

    def fake_emit(ep_id: str, state: Any, **kw: Any) -> None:
        captured.append(ep_id)

    strategy = NodeExecutorStrategy(
        executor_lookup=_executor_lookup(),
    )
    ctx = _FakeContext(node_config=node_config)
    # Patch the module-level symbol the strategy imported. resolve_executor
    # is a module-level function in node_executor_strategy; replace it with
    # a lambda that returns our fake executor for any (binding, node_id).
    with (
        patch(
            "lca.framework.graph.strategies.node_executor_strategy.emit_for_node",
            side_effect=fake_emit,
        ),
        patch(
            "lca.framework.graph.strategies.node_executor_strategy.resolve_executor",
            return_value=_FakeNodeExecutor(),
        ),
    ):
        asyncio.run(strategy.execute(ctx, NodeInput(port_values={})))
    return captured


def test_emit_on_exit_produces_events() -> None:
    """Nested ``config.config.emit_on_exit`` fires after dispatch."""
    captured = _run_emit(
        {"config": {"emit_on_exit": ["terminal.commit"]}}
    )
    assert captured == ["terminal.commit"]


def test_emit_on_enter_produces_events() -> None:
    """Nested ``config.config.emit_on_enter`` fires before dispatch."""
    captured = _run_emit(
        {"config": {"emit_on_enter": ["phase.perceive.fold"]}}
    )
    assert captured == ["phase.perceive.fold"]


def test_empty_emits_produce_zero_events() -> None:
    """Empty lists and absent keys both produce zero events."""
    captured_a = _run_emit({"config": {"emit_on_enter": [], "emit_on_exit": []}})
    captured_b = _run_emit({})
    assert captured_a == []
    assert captured_b == []


def test_top_level_emit_falls_back() -> None:
    """Legacy ``config[key]`` shape (hand-built plans) still works."""
    captured = _run_emit({"emit_on_exit": ["terminal.commit"]})
    assert captured == ["terminal.commit"]


def test_dispatcher_failure_is_contained() -> None:
    """An EP whose handler raises must not abort the graph."""

    def explode(ep_id: str, state: Any, **kw: Any) -> None:
        raise RuntimeError("simulated handler failure")

    import asyncio

    strategy = NodeExecutorStrategy(executor_lookup=_executor_lookup())
    ctx = _FakeContext(
        node_config={"config": {"emit_on_exit": ["unknown.ep"]}}
    )
    with (
        patch(
            "lca.framework.graph.strategies.node_executor_strategy.emit_for_node",
            side_effect=explode,
        ),
        patch(
            "lca.framework.graph.strategies.node_executor_strategy.resolve_executor",
            return_value=_FakeNodeExecutor(),
        ),
    ):
        # No exception propagates: dispatcher failure is contained.
        asyncio.run(strategy.execute(ctx, NodeInput(port_values={})))


def test_multiple_emits_fire_in_order() -> None:
    """Multiple EPs in one list fire in declaration order."""
    captured = _run_emit(
        {"config": {"emit_on_exit": ["phase.act.fold.end", "terminal.commit"]}}
    )
    assert captured == ["phase.act.fold.end", "terminal.commit"]