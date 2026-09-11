"""SubgraphStrategy — recursive entry into another :class:`Plan`.

A :class:`lca.contracts.protocols.graph.plan.SubgraphReference` on a node
points to another plan. The strategy delegates to a host-injected
``recursive_runner`` callable that takes ``(sub_plan, outer_state,
depth, outer_ports)`` and returns a ``Mapping[str, Any]`` of merged
output port values. ``outer_ports`` is a :class:`PortRegistry` seeded
from this node's :attr:`NodeInput.port_values` (via
:meth:`PortRegistry.set_outer_input`) so edges like
``sub_spec_ref`` can forward upstream values across the subgraph
boundary; it is ``None`` when the outer node carried no port values.

Production callers (post kernel-native cutover, note
2026-09-11-kernel-native-phase-runner) inject a closure that:
1. Loads the bundle YAML referenced by ``ref.plan_ref``.
2. Lifts it into a :class:`Plan` via ``lift_graph_spec``.
3. Calls :meth:`PlanInterpreter.run` recursively against the
   strategy registry's executor for that sub-plan.

The legacy ``sub_runner`` shim from
:class:`lca.framework.subgraph.plugins.runner.SubgraphRunner` is no
longer reachable after PR-9 deletes the framework/subgraph directory.
The kernel-native recursive runner is the sole production path.

The strategy enforces the recursion budget (default 4) via the
host-provided ``depth_counter`` so the bound is the same regardless of
which interpreter is on top.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from inspect import isawaitable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategy_registry import register_strategy

if TYPE_CHECKING:
    pass

RecursiveRunner = Callable[
    [Plan, AgentState, int, "PortRegistry | None"],
    "Mapping[str, Any] | Awaitable[Mapping[str, Any]]",
]
"""Host-injected closure that recurses into a subgraph plan.

The closure takes the sub-:class:`Plan`, the outer :class:`AgentState`,
the current depth, and an optional :class:`PortRegistry` seeded from
the outer node's :attr:`NodeInput.port_values` (via
:meth:`PortRegistry.set_outer_input`). It returns a mapping of merged
output port values (sync) or an awaitable that resolves to one (async).
The strategy awaits the result if it is awaitable. Production closures
are async because :meth:`PlanInterpreter.run` is async. The fourth
argument is ``None`` when the outer node carried no port values, so
the inner plan starts from a fresh empty registry.
"""


@dataclass(frozen=True, slots=True)
class SubgraphStrategy(NodeStrategy):
    """Recursive :class:`Plan` invocation.

    ``recursive_runner`` is host-injected. ``depth_counter`` returns
    the next depth (current + 1) so the host enforces the recursion
    bound.
    """

    kind: BindingKind = BindingKind.SUBGRAPH
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    recursive_runner: RecursiveRunner | None = None
    max_depth: int = 4
    depth_counter: Callable[[], int] | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.recursive_runner is None:
            raise RuntimeError(
                "SubgraphStrategy.execute called without recursive_runner; "
                "the host must inject one (typically the kernel-native "
                "recursive PlanInterpreter.run closure)"
            )
        ref = context.subgraph_ref
        if ref is None:
            raise RuntimeError(
                f"node {context.node_id!r} has binding=SUBGRAPH but no subgraph_ref"
            )
        outer_state = context.node_config.get("agent_state")
        if not isinstance(outer_state, AgentState):
            outer_state = AgentState(trace_id="", task="", budget=_empty_budget())
        depth = 1
        if self.depth_counter is not None:
            depth = self.depth_counter() + 1
        if depth > self.max_depth:
            raise RuntimeError(
                f"subgraph recursion exceeded max_depth={self.max_depth} at "
                f"plan_ref={context.plan_ref!r} node_id={context.node_id!r}"
            )
        sub_plan = _load_subgraph_plan(ref.plan_ref, ref.entry_node)
        outer_ports: PortRegistry | None = None
        if input.port_values:
            outer_ports = PortRegistry()
            outer_ports.set_outer_input(input.port_values)
        outcome = self.recursive_runner(sub_plan, outer_state, depth, outer_ports)
        if isawaitable(outcome):
            outcome = await outcome
        merged_output: Mapping[str, Any] = outcome  # type: ignore[assignment]
        return NodeOutput(
            port_values=dict(merged_output),
            producer_node=context.node_id,
        )


def _load_subgraph_plan(plan_ref: str, entry_node: str) -> Plan:
    """Load a bundle YAML and lift it into a :class:`Plan`.

    Mirrors the legacy ``lift_subgraph_reference_to_v2`` seam: load
    the bundle YAML from ``<repo_root>/<plan_ref>`` and lift it via
    :func:`lift_graph_spec`. The resulting :class:`Plan` is the
    recursive-runner input.
    """
    import yaml

    from lca.framework.graph.lifter import lift_graph_spec

    repo_root = _repo_root()
    path = repo_root / plan_ref
    if not path.is_file():
        raise FileNotFoundError(f"bundle graph yaml not found: {plan_ref}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(
            f"bundle graph yaml must be a mapping at top level, "
            f"got {type(raw).__name__}"
        )
    spec = dict(raw)
    if "entry" not in spec and entry_node:
        spec["entry"] = entry_node
    return lift_graph_spec(spec)


def _repo_root() -> Path:
    """Find the repo root by walking up from this file."""
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "bundles").is_dir():
            return parent
    return Path.cwd()


def _empty_budget() -> Budget:
    return Budget()


register_strategy(SubgraphStrategy())


__all__ = ["RecursiveRunner", "SubgraphStrategy"]
