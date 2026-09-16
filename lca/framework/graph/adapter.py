"""PlanInterpreterAdapter — thin production seam over PlanInterpreter.

Architecture review C2 (Strong): host composition lives in
:mod:`lca.framework.graph.host_wiring`; visit semantics stay in
:class:`PlanInterpreter`. This module is the DeclarativeInterpreter
facade only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.framework.graph.host_wiring import (
    LegacyResultShim as _LegacyResultShim,
)
from lca.framework.graph.host_wiring import (
    NodeRuntimeViewFactory,
    current_graph_depth,
    make_node_executor_lookup,
    make_node_runtime_view_factory,
    make_recursive_runner,
)
from lca.framework.graph.host_wiring import (
    build_registry as _build_registry,
)
from lca.framework.graph.host_wiring import (
    default_graph_clock as _default_graph_clock,
)
from lca.framework.graph.host_wiring import (
    enter_subgraph as _enter_subgraph,
)
from lca.framework.graph.host_wiring import (
    exit_subgraph as _exit_subgraph,
)
from lca.framework.graph.host_wiring import (
    legacy_result_shim as _legacy_result_shim,
)
from lca.framework.graph.host_wiring import (
    plan_entry_id as _plan_entry_id,
)
from lca.framework.graph.host_wiring import (
    seed_traversal as _seed_traversal,
)
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import lift_executable_plan
from lca.framework.graph.observation import GraphObserver, NullGraphObserver
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategies.subgraph_strategy import RecursiveRunner
from lca.framework.graph.strategy_registry import (
    NodeExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
)


def _resolve_default_port_registry_seed(scope: Any) -> dict[str, Any]:
    """Build the production kernel seed for the outer plan's ``PortRegistry``.

    ADR-0241 §2: the kernel seeds two kernel-owned typed ports so the
    outer plan and every subgraph downstream can read them by name on
    any node that declares them as ``declared_inputs``:

    - ``tools`` — resolved from ``scope.get("tools")`` where ``scope``
      is the Cordis runtime carrier published on every visit (the same
      path that already exposes ``effect_gateway``).
    - ``bindings`` — resolved from the typed runtime-plane seam
      ``RuntimePlane.current_bindings_view()`` (ADR-0220 §7.3), which
      replaces the legacy ``AgentState._xxx_ref`` reflection.

    Either may be absent; the kernel only seeds what is bound. Both
    lookups are local and idempotent, safe to call at every outer
    plan entry.
    """
    seed: dict[str, Any] = {}
    if scope is not None:
        getter = getattr(scope, "get", None) or getattr(scope, "resolve", None)
        if callable(getter):
            try:
                tools_service = getter("tools")
            except (KeyError, AttributeError, TypeError):
                tools_service = None
            if tools_service is not None:
                seed["tools"] = tools_service
    try:
        from lca.infrastructure.runtime_plane.capability_bindings import (
            current_bindings_view,
        )

        bindings_view = current_bindings_view()
    except Exception:
        bindings_view = None
    if bindings_view is not None:
        seed["bindings"] = bindings_view
    return seed


def _port_registry_seed_for(
    *,
    seed: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None,
    scope: Any,
) -> dict[str, Any]:
    """Normalize the kernel-seed input into a single ``set_outer_input`` payload.

    - ``Mapping`` → used directly (test injection).
    - ``Callable`` → invoked once at outer plan entry.
    - ``None`` → fall back to production seam (``scope.get("tools")`` +
      ``RuntimePlane.current_bindings_view()``).
    """
    if seed is None:
        return _resolve_default_port_registry_seed(scope)
    if callable(seed):
        produced = seed()
        return dict(produced)
    return dict(seed)


@dataclass(frozen=True, slots=True)
class PhaseRunCursor:
    """Checkpoint cursor passed to :meth:`PlanInterpreterAdapter.resume`."""

    current_node_id: str
    visited_nodes: tuple[str, ...] = ()


@dataclass
class PlanInterpreterAdapter:
    """Thin adapter: lift + host wiring → :class:`PlanInterpreter`."""

    registry: StrategyRegistry | None = None
    executor_lookup: NodeExecutorLookup | None = None
    journal: Any = None
    effect_gateway: Any = None
    reducer: Any = None
    phase_observer: Any = None
    lifecycle_publisher: Any = None
    loop_guard_evaluator: Any = None
    capabilities: Any = None
    node_executors: Mapping[str, Any] | None = None
    node_executor_runtime_scope: Any = None
    graph_observer: GraphObserver | None = None
    graph_clock: Callable[[], int] | None = None
    _phase_results: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.graph_observer is None:
            self.graph_observer = NullGraphObserver()
        if self.graph_clock is None:
            self.graph_clock = _default_graph_clock
        if self.registry is None:
            self.registry = _build_registry(
                make_recursive_runner(self),
                self._depth,
                make_node_executor_lookup(self.node_executors),
                make_node_runtime_view_factory(
                    base_scope=self.node_executor_runtime_scope,
                    effect_gateway=self.effect_gateway,
                ),
                self.graph_observer,
                self.graph_clock,
                default_strategy_registry(),
            )

    def _build_recursive_runner(self) -> RecursiveRunner:
        return make_recursive_runner(self)

    def _depth(self) -> int:
        return current_graph_depth()

    def _build_node_executor_lookup(self) -> NodeExecutorLookup:
        return make_node_executor_lookup(self.node_executors)

    def _build_node_runtime_view_factory(self) -> NodeRuntimeViewFactory:
        return make_node_runtime_view_factory(
            base_scope=self.node_executor_runtime_scope,
            effect_gateway=self.effect_gateway,
        )

    async def run(
        self,
        executable: object,
        *,
        state: object = None,
        outer_state: object = None,
        traversal: object = None,
        input: object = None,
        budget: object = None,
        capabilities: object = None,
        artifacts: object = None,
        spec: object = None,
        port_registry_seed: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None = None,
    ) -> object:
        plan = lift_executable_plan(executable)
        seeded_state = state if outer_state is None else outer_state
        interp = PlanInterpreter(
            registry=self.registry or default_strategy_registry(),
            observer=self.graph_observer,
            clock=self.graph_clock,
            artifacts=artifacts or {},
            results_by_phase=self._phase_results,
        )
        registry = PortRegistry()
        seed = _port_registry_seed_for(
            seed=port_registry_seed, scope=self.node_executor_runtime_scope
        )
        if seed:
            registry.set_outer_input(seed)
        result = await interp.run(
            plan,
            outer_state=seeded_state,
            traversal=traversal,
            port_registry=registry,
        )
        return _legacy_result_shim(state=seeded_state, result=result)

    async def resume(
        self,
        executable: object,
        *,
        state: object = None,
        cursor: object,
        outer_state: object = None,
        input: object = None,
        budget: object = None,
        capabilities: object = None,
        artifacts: object = None,
        spec: object = None,
        port_registry_seed: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None = None,
    ) -> object:
        seeded_state = state if outer_state is None else outer_state
        plan = lift_executable_plan(executable)
        if cursor is None or not getattr(cursor, "current_node_id", ""):
            return await self.run(
                executable,
                state=seeded_state,
                outer_state=seeded_state,
                input=input,
                budget=budget,
                capabilities=capabilities,
                artifacts=artifacts,
                spec=spec,
                port_registry_seed=port_registry_seed,
            )
        start_id = getattr(cursor, "current_node_id", "") or _plan_entry_id(plan)
        visited = tuple(getattr(cursor, "visited_nodes", ()) or ())
        interp = PlanInterpreter(
            registry=self.registry or default_strategy_registry(),
            observer=self.graph_observer,
            clock=self.graph_clock,
            artifacts=artifacts or {},
            results_by_phase=self._phase_results,
        )
        seeded = _seed_traversal(plan, start_id, visited)
        registry = PortRegistry()
        seed = _port_registry_seed_for(
            seed=port_registry_seed, scope=self.node_executor_runtime_scope
        )
        if seed:
            registry.set_outer_input(seed)
        result = await interp.run(
            plan,
            outer_state=seeded_state,
            traversal=seeded,
            port_registry=registry,
        )
        return _legacy_result_shim(state=seeded_state, result=result)


__all__ = [
    "NodeRuntimeViewFactory",
    "PhaseRunCursor",
    "PlanInterpreterAdapter",
    "_LegacyResultShim",
    "_enter_subgraph",
    "_exit_subgraph",
]
