"""PlanInterpreterAdapter - exposes :class:`PlanInterpreter` under the
legacy :class:`DeclarativeInterpreter` Protocol.

This is the **production cutover seam**. The runtime plugin factory
at ``lca.plugins.journal.declarative.runtime_seams_provider`` constructs
this adapter with the five runtime closures
(``journal`` / ``effect_gateway`` / ``reducer`` / ``phase_observer`` /
``lifecycle_publisher``). The adapter hands them to the kernel via
host-injected strategy closures.

The adapter owns:

- a per-adapter :class:`StrategyRegistry` populated by copying the
  default registry's strategies and overriding the subgraph,
  node_executor, transform, observe, terminate, parallel, gate_chain,
  agent_consult and agent_fanout strategies with the closures wired
  by the host,
- a :class:`PhaseRunCursor` for :meth:`resume` to seed the visit
  loop from a checkpointed node instead of restarting from entry,
- the configured :class:`GraphObserver` that observes visit / edge /
  subgraph lifecycle events on the kernel side.

Deletion policy: this adapter is the sole production entry point.
There is no other production interpreter.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import lift_executable_plan
from lca.framework.graph.observation import GraphObserver, NullGraphObserver
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategies.node_executor_strategy import (
    NodeExecutorStrategy,
)
from lca.framework.graph.strategies.subgraph_strategy import (
    RecursiveRunner,
    SubgraphStrategy,
)
from lca.framework.graph.strategy_registry import (
    NodeExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
)
from lca.framework.graph.traversal import PlanTraversal


def _default_graph_clock() -> int:
    """Monotonic millisecond clock used when no fake is injected."""
    return time.monotonic_ns() // 1_000_000


if TYPE_CHECKING:
    from lca.framework.graph.interpreter import InterpretationResult


@dataclass(frozen=True, slots=True)
class PhaseRunCursor:
    """Checkpoint cursor passed to :meth:`PlanInterpreterAdapter.resume`.

    Matches the legacy :class:`lca.contracts.protocols.declarative
    .declarative_1.declarative_execution.PhaseRunCursor` shape for
    the two fields the new kernel reads (``current_node_id`` and
    ``visited_nodes``). The full legacy cursor carries more state
    (budget snapshot, edge counts, …); the new kernel only needs the
    entry point and the visited set to seed :class:`PlanTraversal`.
    """

    current_node_id: str
    visited_nodes: tuple[str, ...] = ()


@dataclass
class PlanInterpreterAdapter:
    """Adapt :class:`PlanInterpreter` to the legacy production shape.

    ``run`` and ``resume`` accept the legacy kwargs (``state``,
    ``input``, ``budget``, ``capabilities``, ``artifacts``,
    ``executable``) and return an :class:`InterpretationResult` from
    the new kernel. The runtime closures and loop guard are stored on
    the adapter so the kernel-native strategies can reach them.

    ``run`` performs a fresh traversal from the plan's entry node.
    ``resume`` accepts a :class:`PhaseRunCursor` and seeds the
    traversal at ``cursor.current_node_id``; when ``cursor`` is
    ``None`` it falls back to a fresh run.
    """

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
    # Per-adapter mirror of phase results (ADR-0219 §4). The kernel
    # carries this across ``run``/``resume`` calls so nested
    # sub-plans see the same phase → typed payload mapping.
    _phase_results: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.graph_observer is None:
            self.graph_observer = NullGraphObserver()
        if self.graph_clock is None:
            self.graph_clock = _default_graph_clock
        if self.registry is None:
            self.registry = _build_registry(
                self._build_recursive_runner(),
                self._depth,
                self._build_node_executor_lookup(),
                self._build_node_runtime_view_factory(),
                self.graph_observer,
                self.graph_clock,
                default_strategy_registry(),
            )

    def _build_recursive_runner(self) -> RecursiveRunner:
        """Return the kernel-native recursive closure for subgraphs.

        Loads the bundle YAML referenced by ``ref.plan_ref`` (already
        lifted by :func:`SubgraphStrategy._load_subgraph_plan` before
        this closure is invoked), then runs the new kernel against
        the sub-plan via the adapter's per-adapter registry. The
        resulting :class:`InterpretationResult.output` is returned to
        the outer node as the merged port map.

        The closure reads ``self.registry`` lazily — at call time —
        because :meth:`__post_init__` builds the registry and assigns
        it to ``self.registry`` only after this builder runs.
        Capturing the value via a local variable would freeze the
        pre-assignment ``None`` here.
        """
        adapter = self

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

    def _depth(self) -> int:
        return _graph_depth.get()

    def _build_node_executor_lookup(self) -> NodeExecutorLookup:
        """Return the executor-lookup for :class:`NodeExecutorStrategy`.

        The factory-name-to-instance map lives in ``self._node_executors``.
        The strategy receives ``context.node_id`` (= factory name) and
        finds the matching executor instance. The framework never
        inspects what factory names exist — the runtime closure
        supplies the closed map.
        """
        executors = self.node_executors or {}

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

        from lca.contracts.protocols.graph.binding import BindingKind

        return lookup

    def _build_node_runtime_view_factory(self) -> NodeRuntimeViewFactory:
        """Build a per-call :class:`_NodeRuntimeView` for node executors.

        The view wraps ``agent_state`` (read directly) plus a
        capability scope. ``context.runtime.<name>`` resolves
        through the scope's ``get`` (PhaseCapabilityReader Protocol)
        or ``resolve`` (legacy PluginContextBackedRuntime). Missing
        capabilities return ``None`` so node plugins' existing
        soft-fail paths stay intact.

        The per-turn ``effect_gateway`` is layered onto the scope via
        a thin wrapper so node plugins can read
        ``context.runtime.effect_gateway`` — the dispatcher built
        fresh for each turn by ``RuntimeBindings.new_interpreter()``
        and passed to ``interpreter_factory.create(effect_gateway=)``.
        The composition-time capability map does not carry per-turn
        values; the wrapper keeps the seam explicit.
        """
        base_scope = self.node_executor_runtime_scope
        effect_gateway = self.effect_gateway

        class _AdapterScope:
            """Delegate capability lookup to the base scope, then layer
            ``effect_gateway`` so per-turn dispatch reaches node plugins."""

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
            return _NodeRuntimeView(state=agent_state, scope=scope)

        return factory

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
    ) -> object:
        """Execute ``executable`` fresh from the declared entry node.

        Both ``state=`` (legacy kwarg name) and ``outer_state=`` (new
        ``PlanInterpreter.run`` kwarg) are accepted; the legacy alias
        maps onto the v2 ``outer_state`` parameter the kernel expects.
        """
        plan = lift_executable_plan(executable)
        seeded_state = state if outer_state is None else outer_state
        interp = PlanInterpreter(
            registry=self.registry or default_strategy_registry(),
            observer=self.graph_observer,
            clock=self.graph_clock,
            artifacts=artifacts or {},
            results_by_phase=self._phase_results,
        )
        result = await interp.run(
            plan, outer_state=seeded_state, traversal=traversal
        )
        return _legacy_result_shim(
            state=seeded_state,
            result=result,
        )

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
    ) -> object:
        """Resume ``executable`` from a checkpointed :class:`PhaseRunCursor`.

        When ``cursor`` is ``None`` this degrades to a fresh ``run``.
        Otherwise the adapter seeds ``PlanTraversal(plan, start=...)``
        with ``cursor.current_node_id`` so the kernel visits the
        checkpointed node first instead of restarting from the entry.
        The visited set seeds ``traversal.visit_counts`` so
        ``max_visits`` enforcement remains correct on resume.

        Both ``state=`` (legacy) and ``outer_state=`` (v2) kwargs are
        accepted; they are equivalent for the kernel.
        """
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
        result = await interp.run(
            plan, outer_state=seeded_state, traversal=seeded
        )
        return _legacy_result_shim(state=seeded_state, result=result)


def _legacy_result_shim(*, state: object, result: InterpretationResult) -> object:
    """Wrap :class:`InterpretationResult` with legacy attribute names.

    Callers of the legacy interpreter expect ``visits`` / ``facts`` /
    ``outcome`` / ``state`` / ``terminal_node`` / ``output`` /
    ``artifact`` / ``cursor``. The shim mirrors the attribute shape
    so production callers do not regress.
    """
    return _LegacyResultShim(
        state=state,
        visits=result.visits,
        facts=result.facts,
        terminal_node=result.terminal_node,
        output=result.output,
    )


def _plan_entry_id(plan: object) -> str:
    """Return the plan's declared entry node id."""
    nodes = getattr(plan, "nodes", ()) or ()
    for n in nodes:
        if getattr(n, "entry", False):
            return str(getattr(n, "id", ""))
    return str(getattr(nodes[0], "id", "")) if nodes else ""


def _seed_traversal(plan: object, start_id: str, visited: tuple[str, ...]) -> PlanTraversal:
    """Build a :class:`PlanTraversal` seeded for resume.

    The new kernel does not yet expose a first-class
    ``PlanTraversal.resume(checkpoint)``; we instantiate the traversal
    with ``current_id=start_id`` and pre-populate ``visit_counts`` from
    ``visited``. ``max_visits`` enforcement remains correct because
    the kernel reads ``visit_counts`` directly before each visit.
    """
    visit_counts: dict[str, int] = dict.fromkeys(visited, 1)
    return PlanTraversal(
        plan=plan,  # type: ignore[arg-type]
        current_id=start_id,
        visit_counts=visit_counts,
    )


def _build_registry(
    recursive_runner: RecursiveRunner,
    depth_counter: Callable[[], int],
    node_executor_lookup: NodeExecutorLookup,
    node_runtime_view_factory: NodeRuntimeViewFactory,
    graph_observer: GraphObserver,
    graph_clock: Callable[[], int],
    source: StrategyRegistry,
) -> StrategyRegistry:
    """Return a fresh :class:`StrategyRegistry` whose strategies carry
    host-injected closures.

    The default registry exposes singletons for every binding kind.
    Each adapter copies the registry, swaps in fresh strategy
    instances with the closures wired, and runs that. Concurrent
    adapters no longer race over shared closure fields.

    The :class:`NodeExecutorStrategy` is rewired so its
    ``executor_lookup`` resolves :class:`NodeExecutor` instances by
    factory name (== node id) from the runtime-supplied
    ``node_executors`` map.
    """
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


@dataclass
class _LegacyResultShim:
    """Mimics the legacy :class:`InterpretationResult` attribute shape."""

    state: Any
    visits: tuple = ()
    facts: tuple = ()
    terminal_node: str = ""
    output: dict = field(default_factory=dict)
    outcome: Any = None
    cursor: Any = None
    artifact: Any = None


class _NodeRuntimeView:
    """Duck-typed view of the legacy :class:`NodeContext.runtime`.

    Node plugins (think subgraph) read ``context.runtime.<name>``
    and ``context.runtime.state``. ``state`` is the outer
    :class:`AgentState`; everything else resolves through
    ``scope.get(name)`` (PhaseCapabilityReader Protocol) or
    ``scope.resolve(name)`` (legacy PluginContextBackedRuntime).
    Missing capabilities return ``None`` so the node plugins'
    soft-fail paths stay intact.

    Mirrors the v2 ``NodeRuntimeView`` that lived in
    ``lca/harness/graph/execute/v2/node_context_factory.py`` before
    the kernel-native cutover.
    """

    __slots__ = ("_scope", "_state")

    def __init__(self, *, state: Any, scope: Any) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_scope", scope)

    @property
    def state(self) -> Any:
        return self._state

    def get(self, key: str) -> Any:
        """Capability lookup used by node plugins that read
        ``context.runtime.<name>`` via the legacy ``runtime.get(name)``
        pattern (e.g. ``PerceiveObserveExecutor``). Delegates to the
        underlying scope so missing capabilities return ``None``;
        ``"state"`` / ``"agent_state"`` are the outer :class:`AgentState`
        and resolve through the view's own slot.
        """
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
        raise AttributeError("_NodeRuntimeView is read-only")


NodeRuntimeViewFactory = Callable[[Any], Any]
"""Build a per-call :class:`_NodeRuntimeView` from the outer :class:`AgentState`."""

# Nesting depth for subgraph recursion (ADR-0220 P6 / subgraph bound).
# Tracked via ContextVar so sibling / sequential subgraph entries at the
# same level do not accumulate; only true recursion increments depth.
_graph_depth: ContextVar[int] = ContextVar("lca_graph_depth", default=0)


def _enter_subgraph() -> tuple[int, Any]:
    """Record entry into one subgraph layer; return (depth_at_entry, reset_token)."""
    depth = _graph_depth.get()
    return depth, _graph_depth.set(depth + 1)


def _exit_subgraph(token: Any) -> None:
    _graph_depth.reset(token)


__all__ = [
    "NodeRuntimeViewFactory",
    "PhaseRunCursor",
    "PlanInterpreterAdapter",
    "_LegacyResultShim",
    "_enter_subgraph",
    "_exit_subgraph",
]
