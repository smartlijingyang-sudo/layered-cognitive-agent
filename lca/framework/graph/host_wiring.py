"""Host wiring for :class:`PlanInterpreterAdapter`.

Architecture review C2 (Strong): host composition (registry rebuild,
recursive runner, node runtime view, subgraph depth ContextVar) lives
here — outside the thin adapter seam and outside the visit loop in
:class:`PlanInterpreter`.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from lca.framework.graph.interpreter import InterpretationResult, PlanInterpreter
from lca.framework.graph.observation import GraphObserver
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategies.node_executor_strategy import NodeExecutorStrategy
from lca.framework.graph.strategies.subgraph_strategy import (
    RecursiveRunner,
    SubgraphStrategy,
)
from lca.framework.graph.strategy_registry import (
    NodeExecutorLookup,
    StrategyRegistry,
)
from lca.framework.graph.traversal import PlanTraversal

NodeRuntimeViewFactory = Callable[[Any], Any]
"""Build a per-call NodeRuntimeView from the outer AgentState."""


def default_graph_clock() -> int:
    """Monotonic millisecond clock used when no fake is injected."""
    return time.monotonic_ns() // 1_000_000


def build_registry(
    recursive_runner: RecursiveRunner,
    depth_counter: Callable[[], int],
    node_executor_lookup: NodeExecutorLookup,
    node_runtime_view_factory: NodeRuntimeViewFactory,
    graph_observer: GraphObserver,
    graph_clock: Callable[[], int],
    source: StrategyRegistry,
) -> StrategyRegistry:
    """Return a fresh StrategyRegistry whose strategies carry host closures."""
    new_registry = StrategyRegistry()
    for kind in source.kinds():
        strategy = source.resolve(kind)
        if isinstance(strategy, SubgraphStrategy):
            new_registry.register(
                SubgraphStrategy(
                    recursive_runner=recursive_runner,
                    depth_counter=depth_counter,
                    observer=graph_observer,
                    clock=graph_clock,
                )
            )
        elif isinstance(strategy, NodeExecutorStrategy):
            new_registry.register(
                NodeExecutorStrategy(
                    executor_lookup=node_executor_lookup,
                    node_runtime_view_factory=node_runtime_view_factory,
                )
            )
        else:
            new_registry.register(strategy)
    return new_registry


def make_recursive_runner(adapter: Any) -> RecursiveRunner:
    """Kernel-native recursive closure for subgraphs (lazy registry read)."""

    async def recursive_runner(
        sub_plan: Any,
        outer_state: Any,
        depth: int,
        port_registry: PortRegistry | None = None,
        outer_mirror: Mapping[Any, Any] | None = None,
    ) -> Mapping[str, Any]:
        seeded_state = outer_state
        if outer_state is not None and not hasattr(outer_state, "graph_depth"):
            try:
                object.__setattr__(outer_state, "graph_depth", depth)
                seeded_state = outer_state
            except (AttributeError, TypeError):

                class _DepthCarrier:
                    def __init__(self, base: Any, depth: int) -> None:
                        self._base = base
                        self.graph_depth = depth

                    def __getattr__(self, name: str) -> Any:
                        return getattr(self._base, name)

                seeded_state = _DepthCarrier(outer_state, depth)
        interp = PlanInterpreter(
            registry=adapter.registry,
            observer=adapter.graph_observer,
            clock=adapter.graph_clock,
            results_by_phase=outer_mirror if outer_mirror is not None else {},
        )
        result = await interp.run(
            sub_plan, outer_state=seeded_state, port_registry=port_registry
        )
        return dict(result.output)

    return recursive_runner


def make_node_executor_lookup(node_executors: Mapping[str, Any] | None) -> NodeExecutorLookup:
    from lca.contracts.protocols.graph.binding import BindingKind

    executors = node_executors or {}

    def lookup(*, binding: Any, node_id: str, region: str | None) -> Any:
        if binding != BindingKind.NODE_EXECUTOR:
            return None
        executor = executors.get(node_id)
        if executor is None:
            available = ", ".join(sorted(executors))
            raise RuntimeError(
                f"NodeExecutor lookup miss: node_id={node_id!r} "
                f"not in node_executors (have: {available or '<none>'})"
            )
        return executor

    return lookup


def make_node_runtime_view_factory(
    *,
    base_scope: Any,
    effect_gateway: Any,
) -> NodeRuntimeViewFactory:
    class _AdapterScope:
        __slots__ = ("_base", "_effect_gateway")

        def __init__(self, base: Any, effect_gateway: Any) -> None:
            object.__setattr__(self, "_base", base)
            object.__setattr__(self, "_effect_gateway", effect_gateway)

        def get(self, name: str) -> Any:
            if name == "effect_gateway":
                return self._effect_gateway
            base = self._base
            if base is None:
                return None
            getter = getattr(base, "get", None) or getattr(base, "resolve", None)
            if getter is None:
                return None
            try:
                return getter(name)
            except (KeyError, AttributeError, TypeError):
                return None

        def __getattr__(self, name: str) -> Any:
            return getattr(self._base, name)

    scope = _AdapterScope(base_scope, effect_gateway)

    def factory(agent_state: Any) -> Any:
        return NodeRuntimeView(state=agent_state, scope=scope)

    return factory


@dataclass
class LegacyResultShim:
    state: Any
    visits: tuple = ()
    facts: tuple = ()
    terminal_node: str = ""
    output: dict = field(default_factory=dict)
    outcome: Any = None
    cursor: Any = None
    artifact: Any = None


def legacy_result_shim(*, state: object, result: InterpretationResult) -> object:
    return LegacyResultShim(
        state=state,
        visits=result.visits,
        facts=result.facts,
        terminal_node=result.terminal_node,
        output=result.output,
    )


def plan_entry_id(plan: object) -> str:
    nodes = getattr(plan, "nodes", ()) or ()
    for n in nodes:
        if getattr(n, "entry", False):
            return str(getattr(n, "id", ""))
    return str(getattr(nodes[0], "id", "")) if nodes else ""


def seed_traversal(plan: object, start_id: str, visited: tuple[str, ...]) -> PlanTraversal:
    visit_counts: dict[str, int] = dict.fromkeys(visited, 1)
    return PlanTraversal(
        plan=plan,  # type: ignore[arg-type]
        current_id=start_id,
        visit_counts=visit_counts,
    )


class NodeRuntimeView:
    __slots__ = ("_scope", "_state")

    def __init__(self, *, state: Any, scope: Any) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_scope", scope)

    @property
    def state(self) -> Any:
        return self._state

    def get(self, key: str) -> Any:
        if key in ("state", "agent_state"):
            return self._state
        scope = object.__getattribute__(self, "_scope")
        if scope is None:
            return None
        getter = getattr(scope, "get", None)
        if getter is None:
            getter = getattr(scope, "resolve", None)
        if getter is None:
            return None
        try:
            return getter(key)
        except (KeyError, AttributeError, TypeError):
            return None

    def __getattr__(self, key: str) -> Any:
        scope = object.__getattribute__(self, "_scope")
        if scope is None:
            return None
        getter = getattr(scope, "get", None)
        if getter is None:
            getter = getattr(scope, "resolve", None)
        if getter is None:
            return None
        try:
            return getter(key)
        except (KeyError, AttributeError, TypeError):
            return None

    def __setattr__(self, key: str, value: Any) -> None:
        raise AttributeError("NodeRuntimeView is read-only")


_graph_depth: ContextVar[int] = ContextVar("lca_graph_depth", default=0)


def enter_subgraph() -> tuple[int, Any]:
    depth = _graph_depth.get()
    return depth, _graph_depth.set(depth + 1)


def exit_subgraph(token: Any) -> None:
    _graph_depth.reset(token)


def current_graph_depth() -> int:
    return _graph_depth.get()


# Backward-compatible private aliases.
_default_graph_clock = default_graph_clock
_build_registry = build_registry
_LegacyResultShim = LegacyResultShim
_NodeRuntimeView = NodeRuntimeView
_enter_subgraph = enter_subgraph
_exit_subgraph = exit_subgraph

__all__ = [
    "LegacyResultShim",
    "NodeRuntimeView",
    "NodeRuntimeViewFactory",
    "build_registry",
    "current_graph_depth",
    "default_graph_clock",
    "enter_subgraph",
    "exit_subgraph",
    "legacy_result_shim",
    "make_node_executor_lookup",
    "make_node_runtime_view_factory",
    "make_recursive_runner",
    "plan_entry_id",
    "seed_traversal",
    "_LegacyResultShim",
    "_NodeRuntimeView",
    "_build_registry",
    "_default_graph_clock",
    "_enter_subgraph",
    "_exit_subgraph",
]
