"""End-to-end: PlanInterpreter + SpineGraphObserver -> <run_id>.spine.jsonl.

Wires the kernel observer to a real :class:`EventSpine` + :class:`FileSink`
and asserts that visit start / end, edge, and subgraph enter / exit
events land on disk with the full payload the observer carried.

What this catches:
- The observer's ``emit`` callable receives the EP names the
  :class:`GraphEpTable` resolves.
- Each spine record's ``payload`` includes ``inputs`` / ``outputs``
  / ``metadata`` — debug readers must not see silently filtered
  fields.
- The kernel emits visit-start and visit-end as a pair per node;
  an unbalanced pair fails loud here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.plan import (
    Plan,
    PlanEdge,
    PlanNode,
    SubgraphReference,
)
from lca.contracts.protocols.graph.strategy import (
    NodeStrategy,
)
from lca.framework.graph.ep_table import (
    EP_EDGE_TRANSIT,
    EP_NODE_END,
    EP_NODE_START,
    EP_SUBGRAPH_ENTER,
    EP_SUBGRAPH_EXIT,
)
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.observer_impls import SpineGraphObserver
from lca.framework.graph.strategies.subgraph_strategy import SubgraphStrategy
from lca.framework.graph.strategy_registry import (
    StrategyRegistry,
)


class _NoopStrategy(NodeStrategy):
    """Returns an empty ``NodeOutput`` so the kernel advances."""

    kind: BindingKind = BindingKind.NODE_EXECUTOR
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)

    async def execute(self, context, input):  # type: ignore[override]
        return NodeOutput(port_values={}, producer_node=context.node_id)


@dataclass(frozen=True, slots=True)
class _FixedStrategy(NodeStrategy):
    """Always advances to ``next_target``; emits a fixed port."""

    kind: BindingKind = BindingKind.NODE_EXECUTOR
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    payload_value: object = "ok"
    next_target: str = ""

    async def execute(self, context, input):  # type: ignore[override]
        return NodeOutput(
            port_values={"decision": self.payload_value},
            producer_node=context.node_id,
            result_kind="decision",
            next_hints={"next": self.next_target},
        )


def _read_spine_records(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _make_spine(tmp_path: Path, run_id: str) -> tuple[object, object]:
    from lca.infrastructure.observability.spine.event.spine import EventSpine
    from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

    sink = FileSink(tmp_path, run_id=run_id)
    spine = EventSpine(sinks=[sink], run_id=run_id)
    return spine, sink


def _emit_for_spine(spine: object, safe_append_fn: object) -> object:
    """Build the EmitFn that routes one observation through ``_safe_append``."""

    def emit(ep: str, payload: dict) -> None:
        safe_append_fn(
            spine=spine,
            execution_point=ep,
            channel="control",
            payload=payload,
            outcome=None,
            span=None,
        )

    return emit


@pytest.mark.asyncio
async def test_kernel_observer_writes_full_payload_to_run_spine(tmp_path: Path) -> None:
    """Two-node plan visits must produce start/end pairs and one edge on disk."""
    from lca.harness.declarative.compile.instrument.wrap import _safe_append

    run_id = "run-graph-e2e"
    spine, _sink = _make_spine(tmp_path, run_id)
    emit_fn = _emit_for_spine(spine, _safe_append)
    observer = SpineGraphObserver(emit=emit_fn)
    try:
        reg = StrategyRegistry()
        reg.register(_FixedStrategy(payload_value="answer", next_target="b"))
        plan = Plan(
            id="plan-1",
            nodes=(
                PlanNode(id="a", binding=BindingKind.NODE_EXECUTOR, entry=True),
                PlanNode(id="b", binding=BindingKind.NODE_EXECUTOR, terminal=True),
            ),
            edges=(PlanEdge(source="a", target="b"),),
        )
        interp = PlanInterpreter(registry=reg, observer=observer)
        await interp.run(plan)
    finally:
        spine.flush()
        spine.close()

    records = _read_spine_records(tmp_path / f"{run_id}.spine.jsonl")
    eps = [r["execution_point"] for r in records]
    assert eps.count(EP_NODE_START) == 2
    assert eps.count(EP_NODE_END) == 2
    assert eps.count(EP_EDGE_TRANSIT) == 1

    end_a = next(
        r for r in records if r["execution_point"] == EP_NODE_END and r["payload"]["node_id"] == "a"
    )
    payload = end_a["payload"]
    assert payload["kind"] == "visit_end"
    assert payload["outcome"] == "success"
    assert payload["outputs"] == {"decision": "answer"}
    assert payload["inputs"] == {}
    assert payload["metadata"]["binding"] == "node_executor"
    assert payload["elapsed_ms"] >= 0
    assert payload["occurred_at_ms"] > 0


@pytest.mark.asyncio
async def test_subgraph_boundary_emits_enter_and_exit(tmp_path: Path, monkeypatch) -> None:
    """A plan that descends into a subgraph must produce enter/exit pairs."""
    from lca.harness.declarative.compile.instrument.wrap import _safe_append

    run_id = "run-graph-sub"
    spine, _sink = _make_spine(tmp_path, run_id)
    emit_fn = _emit_for_spine(spine, _safe_append)
    observer = SpineGraphObserver(emit=emit_fn)
    try:
        sub_plan = Plan(
            id="inner",
            nodes=(
                PlanNode(id="inner_a", binding=BindingKind.NODE_EXECUTOR, entry=True),
                PlanNode(id="inner_b", binding=BindingKind.NODE_EXECUTOR, terminal=True),
            ),
            edges=(PlanEdge(source="inner_a", target="inner_b"),),
        )
        monkeypatch.setattr(
            "lca.framework.graph.strategies.subgraph_strategy._load_subgraph_plan",
            lambda ref, entry: sub_plan,
        )

        async def runner(plan_, outer_state, depth, outer_ports, outer_mirror=None):
            inner_reg = StrategyRegistry()
            inner_reg.register(_NoopStrategy())
            inner = PlanInterpreter(registry=inner_reg, observer=observer)
            result = await inner.run(plan_, outer_state=outer_state)
            return dict(result.output)

        outer_reg = StrategyRegistry()
        outer_reg.register(_FixedStrategy(payload_value="outer", next_target="recurse"))
        outer_reg.register(
            SubgraphStrategy(
                recursive_runner=runner,
                observer=observer,
            )
        )
        plan = Plan(
            id="outer",
            nodes=(
                PlanNode(id="recurse", binding=BindingKind.SUBGRAPH, entry=True),
                PlanNode(id="end", binding=BindingKind.NODE_EXECUTOR, terminal=True),
            ),
            edges=(PlanEdge(source="recurse", target="end"),),
        )
        plan.nodes[0].__dict__  # noqa: B018 - keep pydantic freeze semantics calm
        plan = plan.model_copy(
            update={
                "nodes": (
                    plan.nodes[0].model_copy(
                        update={
                            "subgraph_ref": SubgraphReference(
                                plan_ref="inner",
                                entry_node="inner_a",
                                binding_edge="e_inner",
                            )
                        }
                    ),
                    plan.nodes[1],
                )
            }
        )
        interp = PlanInterpreter(registry=outer_reg, observer=observer)
        await interp.run(plan)
    finally:
        spine.flush()
        spine.close()

    records = _read_spine_records(tmp_path / f"{run_id}.spine.jsonl")
    eps = [r["execution_point"] for r in records]
    assert EP_SUBGRAPH_ENTER in eps
    assert EP_SUBGRAPH_EXIT in eps
    enter = next(r for r in records if r["execution_point"] == EP_SUBGRAPH_ENTER)
    exit_ = next(r for r in records if r["execution_point"] == EP_SUBGRAPH_EXIT)
    assert enter["payload"]["kind"] == "subgraph_enter"
    assert exit_["payload"]["kind"] == "subgraph_exit"
    assert exit_["payload"]["outcome"] == "success"
    assert enter["payload"]["metadata"]["subgraph_plan_ref"] == "inner"


def _force_module_register() -> None:
    """Touch the strategies so their module-level ``register_strategy`` fires."""
    from lca.framework.graph.strategies import (
        node_executor_strategy,  # noqa: F401
        subgraph_strategy,  # noqa: F401
    )


_force_module_register()
