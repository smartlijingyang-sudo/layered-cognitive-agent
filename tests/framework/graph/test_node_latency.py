"""Contract tests for per-visit node latency tracking (todo-28 C1).

Pins the metric surface landed by quality lane (``lca/framework/graph/
node_latency.py`` + ``PlanInterpreter.latency``):

* ``NodeLatencyTracker``: aggregate math, percentile interpolation, bounded
  retention window, negative clamping, reset semantics, snapshot isolation.
* Wiring: the interpreter records exactly one sample per visit on both the
  success and failure ``visit_end`` paths, with elapsed time measured by the
  interpreter's own clock.

Pure-tracker tests are fully deterministic. Wiring tests drive the real
``PlanInterpreter`` over a single terminal node with a fake clock and
self-contained executor fakes (no kernel, no LLM).
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any
from unittest.mock import patch

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, PlanNode
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.node_latency import NodeLatencyStats, NodeLatencyTracker
from lca.framework.graph.strategy_registry import (
    NodeExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
)

_EMIT_SYMBOL = "lca.loop.emit.node_emitter.emit_for_node"


# ---------------------------------------------------------------------------
# Pure tracker semantics
# ---------------------------------------------------------------------------


def test_record_and_snapshot_aggregates() -> None:
    """count/total/min/max over one node's samples; p50 exact at rank 1.0."""
    tracker = NodeLatencyTracker()
    for sample in (10, 20, 30):
        tracker.record("n", sample)
    stats = tracker.snapshot()["n"]
    assert isinstance(stats, NodeLatencyStats)
    assert (stats.count, stats.total_ms, stats.min_ms, stats.max_ms) == (3, 60, 10, 30)
    assert stats.p50_ms == 20.0
    # rank = (3-1) * 0.95 = 1.9 -> 20 * 0.1 + 30 * 0.9
    assert stats.p95_ms == pytest.approx(29.0)


def test_percentile_interpolates_between_ranks() -> None:
    """Even sample count pins linear interpolation, not nearest-rank."""
    tracker = NodeLatencyTracker()
    for sample in (1, 2, 3, 4):
        tracker.record("n", sample)
    stats = tracker.snapshot()["n"]
    # p50 rank = 3 * 0.5 = 1.5 -> 2 * 0.5 + 3 * 0.5
    assert stats.p50_ms == pytest.approx(2.5)
    # p95 rank = 3 * 0.95 = 2.85 -> 3 * 0.15 + 4 * 0.85
    assert stats.p95_ms == pytest.approx(3.85)


def test_single_sample_percentiles_equal_sample() -> None:
    tracker = NodeLatencyTracker()
    tracker.record("n", 7)
    stats = tracker.snapshot()["n"]
    assert stats.p50_ms == 7.0
    assert stats.p95_ms == 7.0


def test_bounded_window_keeps_newest_samples() -> None:
    """Overflow evicts the oldest samples; aggregates reflect the window."""
    tracker = NodeLatencyTracker(max_samples=4)
    for sample in (1, 2, 3, 4, 5, 6):
        tracker.record("n", sample)
    stats = tracker.snapshot()["n"]
    # retained window is [3, 4, 5, 6], not [1, ..., 6]
    assert (stats.count, stats.total_ms, stats.min_ms, stats.max_ms) == (4, 18, 3, 6)


def test_default_bound_is_4096_samples() -> None:
    """Default cap pins memory: long runs cannot grow samples unbounded."""
    tracker = NodeLatencyTracker()
    for sample in range(5000):
        tracker.record("n", sample)
    stats = tracker.snapshot()["n"]
    assert stats.count == 4096
    # retained window is the newest 4096: [904, ..., 4999]
    assert (stats.min_ms, stats.max_ms) == (904, 4999)
    assert stats.total_ms == sum(range(904, 5000))


def test_negative_elapsed_clamped_to_zero() -> None:
    """A clock that goes backwards cannot poison aggregates."""
    tracker = NodeLatencyTracker()
    tracker.record("n", -5)
    stats = tracker.snapshot()["n"]
    assert (stats.count, stats.total_ms, stats.min_ms) == (1, 0, 0)


def test_reset_opens_new_window() -> None:
    tracker = NodeLatencyTracker()
    tracker.record("n", 10)
    tracker.reset()
    assert tracker.snapshot() == {}
    tracker.record("n", 20)
    stats = tracker.snapshot()["n"]
    assert (stats.count, stats.total_ms) == (1, 20)


def test_fresh_tracker_snapshots_empty() -> None:
    assert NodeLatencyTracker().snapshot() == {}


def test_nodes_are_isolated_from_each_other() -> None:
    tracker = NodeLatencyTracker()
    tracker.record("a", 5)
    tracker.record("b", 10)
    snapshot = tracker.snapshot()
    assert set(snapshot) == {"a", "b"}
    assert snapshot["a"].total_ms == 5
    assert snapshot["b"].total_ms == 10


def test_snapshot_is_a_value_copy() -> None:
    """Mutating a returned snapshot cannot corrupt the tracker's state."""
    tracker = NodeLatencyTracker()
    tracker.record("a", 5)
    snapshot = tracker.snapshot()
    snapshot["a"] = None  # type: ignore[assignment]
    assert tracker.snapshot()["a"].count == 1
    assert tracker.snapshot() == snapshot | {"a": tracker.snapshot()["a"]}


def test_stats_are_frozen() -> None:
    """Stats must be safe to keep: frozen dataclass, no post-hoc mutation."""
    tracker = NodeLatencyTracker()
    tracker.record("n", 5)
    stats = tracker.snapshot()["n"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        stats.total_ms = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Interpreter wiring
# ---------------------------------------------------------------------------


class _FakeClock:
    """Manual ms clock; only advances when the test executor advances it."""

    def __init__(self, start_ms: int = 1_000) -> None:
        self.now_ms = start_ms

    def __call__(self) -> int:
        return self.now_ms

    def advance(self, ms: int) -> None:
        self.now_ms += ms


class _AdvancingExecutor:
    """Echo executor that advances the fake clock by a fixed amount."""

    semantic_name = "test.advance"
    declared_inputs: tuple[str, ...] = ()
    declared_outputs: tuple[str, ...] = ()

    def __init__(self, clock: _FakeClock, advance_ms: int) -> None:
        self._clock = clock
        self._advance_ms = advance_ms

    async def node_execute(self, ctx: Any, input: Any) -> Any:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeOutput as LegacyNodeOutput,
        )

        self._clock.advance(self._advance_ms)
        return LegacyNodeOutput(port_values=dict(input.port_values))


class _AdvancingRaiser:
    """Executor that advances the clock, then fails the visit."""

    semantic_name = "test.advance_raise"
    declared_inputs: tuple[str, ...] = ()
    declared_outputs: tuple[str, ...] = ()

    def __init__(self, clock: _FakeClock, advance_ms: int) -> None:
        self._clock = clock
        self._advance_ms = advance_ms

    async def node_execute(self, ctx: Any, input: Any) -> Any:
        self._clock.advance(self._advance_ms)
        raise RuntimeError("simulated node body failure")


def _registry(executor: Any) -> StrategyRegistry:
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


def _single_node_plan() -> Plan:
    node = PlanNode(
        id="test.node",
        binding=BindingKind.NODE_EXECUTOR,
        terminal=True,
        io_schema=NodeIOSchema(outputs=()),
        config={},
    )
    return Plan(id="test.plan", nodes=(node.model_copy(update={"entry": True}),), edges=())


def _interpret(interpreter: PlanInterpreter) -> None:
    with patch(_EMIT_SYMBOL, side_effect=lambda ep_id, state, **kw: None):
        asyncio.run(interpreter.run(_single_node_plan(), outer_state=None, port_registry_seed={}))


def test_successful_visit_records_exact_elapsed() -> None:
    """Success path: one sample, elapsed = interpreter-clock delta."""
    clock = _FakeClock()
    interpreter = PlanInterpreter(registry=_registry(_AdvancingExecutor(clock, 42)), clock=clock)
    _interpret(interpreter)
    stats = interpreter.latency.snapshot()["test.node"]
    assert isinstance(stats, NodeLatencyStats)
    assert stats.count == 1
    assert (stats.total_ms, stats.min_ms, stats.max_ms) == (42, 42, 42)


def test_failing_visit_still_records_latency() -> None:
    """Failure path also records (the metric must not silently drop errors)."""
    clock = _FakeClock()
    interpreter = PlanInterpreter(registry=_registry(_AdvancingRaiser(clock, 17)), clock=clock)
    with (
        patch(_EMIT_SYMBOL, side_effect=lambda ep_id, state, **kw: None),
        pytest.raises(RuntimeError, match="simulated node body failure"),
    ):
        asyncio.run(interpreter.run(_single_node_plan(), outer_state=None, port_registry_seed={}))
    stats = interpreter.latency.snapshot()["test.node"]
    assert (stats.count, stats.total_ms) == (1, 17)


def test_interpreters_do_not_share_trackers() -> None:
    """The latency field is a default_factory: no cross-run leakage."""
    clock_a, clock_b = _FakeClock(), _FakeClock()
    first = PlanInterpreter(registry=_registry(_AdvancingExecutor(clock_a, 1)), clock=clock_a)
    second = PlanInterpreter(registry=_registry(_AdvancingExecutor(clock_b, 1)), clock=clock_b)
    assert first.latency is not second.latency
