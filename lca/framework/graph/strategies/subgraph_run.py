"""Subgraph nested-run — resolve, interpret, merge, observe.

Architecture review C3 (Worth exploring): nested-run policy, port
merge, and observation live behind :class:`SubgraphRun`. The strategy
is a thin dispatcher.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from inspect import isawaitable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.graph.node_io import NodeInput, NodeIOSchema, NodeOutput
from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph.observation import (
    KIND_SUBGRAPH_ENTER,
    KIND_SUBGRAPH_EXIT,
    GraphObservation,
    GraphObserver,
    NullGraphObserver,
)
from lca.framework.graph.port_registry import PortRegistry

RecursiveRunner = Callable[
    [Plan, AgentState, int, "PortRegistry | None", "Mapping | None"],
    "Mapping[str, Any] | Awaitable[Mapping[str, Any]]",
]


@runtime_checkable
class SubgraphRun(Protocol):
    async def run(self, context: StrategyContext, input: NodeInput) -> NodeOutput: ...


@dataclass
class DefaultSubgraphRun:
    recursive_runner: RecursiveRunner
    max_depth: int = 4
    depth_counter: Callable[[], int] | None = None
    observer: GraphObserver = field(default_factory=NullGraphObserver)
    clock: Callable[[], int] | None = None

    async def run(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
        ref = context.subgraph_ref
        if ref is None:
            raise RuntimeError(
                f"node {context.node_id!r} has binding=SUBGRAPH but no subgraph_ref"
            )
        outer_state = context.node_config.get("agent_state")
        if not isinstance(outer_state, AgentState):
            outer_state = AgentState(trace_id="", task="", budget=_empty_budget())
        outer_mirror = context.node_config.get("results_by_phase") or {}
        depth = 1
        depth_token: Any = None
        if self.depth_counter is not None:
            from lca.framework.graph.host_wiring import enter_subgraph, exit_subgraph
            current_depth, depth_token = enter_subgraph()
            depth = current_depth + 1
        if depth > self.max_depth:
            if depth_token is not None:
                from lca.framework.graph.host_wiring import exit_subgraph
                exit_subgraph(depth_token)
            raise RuntimeError(
                f"subgraph recursion exceeded max_depth={self.max_depth} at "
                f"plan_ref={context.plan_ref!r} node_id={context.node_id!r}"
            )
        sub_plan = load_subgraph_plan(ref.plan_ref, ref.entry_node)
        translated_input = translate_inputs(context, input)
        outer_ports: PortRegistry | None = None
        if translated_input:
            outer_ports = PortRegistry()
            outer_ports.set_outer_input(translated_input)
        observe_enter(self.observer, self.clock, context, ref, depth)
        try:
            outcome = self.recursive_runner(
                sub_plan, outer_state, depth, outer_ports, outer_mirror
            )
            if isawaitable(outcome):
                outcome = await outcome
        except BaseException as exc:
            observe_exit(
                self.observer, self.clock, context, ref, depth,
                outcome="failure", error=repr(exc),
            )
            if depth_token is not None:
                from lca.framework.graph.host_wiring import exit_subgraph
                exit_subgraph(depth_token)
            raise
        merged_output: Mapping[str, Any] = outcome  # type: ignore[assignment]
        outer_output = translate_outputs(context, merged_output)
        observe_exit(
            self.observer, self.clock, context, ref, depth,
            outcome="success", error="",
        )
        if depth_token is not None:
            from lca.framework.graph.host_wiring import exit_subgraph
            exit_subgraph(depth_token)
        return NodeOutput(port_values=outer_output, producer_node=context.node_id)


def translate_inputs(context: StrategyContext, input: NodeInput) -> dict[str, Any]:
    inner_schema = context.inner_io_schema
    outer_input_names: tuple[str, ...] = tuple(input.port_values.keys())
    translated_input: dict[str, Any] = dict(input.port_values)
    if inner_schema is not None and inner_schema.inputs:
        inner_input_names = tuple(p.name for p in inner_schema.inputs)
        if len(outer_input_names) == len(inner_input_names):
            translated_input = {
                inner_input_names[i]: input.port_values[outer_input_names[i]]
                for i in range(len(outer_input_names))
            }
        elif outer_input_names and not inner_input_names:
            translated_input = dict(input.port_values)
        elif inner_input_names and not outer_input_names:
            translated_input = {}
    return translated_input


def translate_outputs(context: StrategyContext, merged_output: Mapping[str, Any]) -> dict[str, Any]:
    outer_output: dict[str, Any] = dict(merged_output)
    outer_declared_outputs = outer_declared_outputs_of(context)
    inner_schema = context.inner_io_schema
    if inner_schema is not None and inner_schema.outputs and outer_declared_outputs:
        inner_output_names = tuple(p.name for p in inner_schema.outputs)
        if len(outer_declared_outputs) == len(inner_output_names):
            translated = {
                outer_declared_outputs[i]: merged_output.get(inner_output_names[i])
                for i in range(len(outer_declared_outputs))
                if inner_output_names[i] in merged_output
            }
            if translated:
                outer_output = translated
    if outer_declared_outputs and len(outer_output) != len(outer_declared_outputs):
        direct_mapped = {}
        for outer_name in outer_declared_outputs:
            if outer_name in merged_output:
                direct_mapped[outer_name] = merged_output[outer_name]
        if direct_mapped:
            outer_output = direct_mapped
    return outer_output


def outer_declared_outputs_of(context: StrategyContext) -> tuple[str, ...]:
    declared = context.node_config.get("declared_outputs") if context.node_config else None
    if isinstance(declared, (list, tuple)) and declared:
        return tuple(str(name) for name in declared)
    return ()


def load_subgraph_plan(plan_ref: str, entry_node: str) -> Plan:
    import yaml
    from lca.framework.graph.lifter import _lift_graph_spec_inner, validate_predicates
    path = repo_root() / plan_ref
    if not path.is_file():
        raise FileNotFoundError(f"bundle graph yaml not found: {plan_ref}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(
            f"bundle graph yaml must be a mapping at top level, got {type(raw).__name__}"
        )
    spec = dict(raw)
    if "entry" not in spec and entry_node:
        spec["entry"] = entry_node
    plan = _lift_graph_spec_inner(spec)
    validate_predicates(plan)
    return plan


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "bundles").is_dir():
            return parent
    return Path.cwd()


def observe_enter(observer, clock, context, ref, depth) -> None:
    observer.observe(
        GraphObservation(
            kind=KIND_SUBGRAPH_ENTER,
            plan_ref=context.plan_ref,
            occurred_at_ms=_now_ms(clock),
            node_id=context.node_id,
            depth=depth,
            metadata=(
                ("entry_node", ref.entry_node),
                ("subgraph_plan_ref", ref.plan_ref),
                ("binding_edge", ref.binding_edge),
                ("return_on", ref.return_on),
            ),
        )
    )


def observe_exit(observer, clock, context, ref, depth, *, outcome, error) -> None:
    observer.observe(
        GraphObservation(
            kind=KIND_SUBGRAPH_EXIT,
            plan_ref=context.plan_ref,
            occurred_at_ms=_now_ms(clock),
            node_id=context.node_id,
            depth=depth,
            outcome=outcome,
            error=error,
            metadata=(
                ("entry_node", ref.entry_node),
                ("subgraph_plan_ref", ref.plan_ref),
                ("binding_edge", ref.binding_edge),
            ),
        )
    )


def _now_ms(clock):
    if clock is None:
        import time as _time
        return _time.monotonic_ns() // 1_000_000
    return clock()


def _empty_budget() -> Budget:
    return Budget()


_load_subgraph_plan = load_subgraph_plan
_outer_declared_outputs = outer_declared_outputs_of
_repo_root = repo_root

__all__ = [
    "DefaultSubgraphRun", "RecursiveRunner", "SubgraphRun",
    "load_subgraph_plan", "outer_declared_outputs_of", "repo_root",
    "translate_inputs", "translate_outputs",
    "_load_subgraph_plan", "_outer_declared_outputs", "_repo_root",
]
