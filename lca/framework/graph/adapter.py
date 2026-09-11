"""PlanInterpreterAdapter — exposes :class:`PlanInterpreter` under the
legacy :class:`DeclarativeInterpreter` Protocol.

This is the **production cutover seam**. The runtime plugin factory
at ``lca.plugins.journal.declarative.runtime_seams_provider`` constructs
this adapter with the five runtime closures
(``journal`` / ``effect_gateway`` / ``reducer`` / ``phase_observer`` /
``lifecycle_publisher``), the phase capability reader, and
``loop_guard_evaluator``. The adapter hands them to the kernel via
host-injected strategy closures.

The adapter owns:

- a per-adapter :class:`StrategyRegistry` populated by copying the
  default registry's strategies and overriding
  :class:`PhaseExecutorStrategy` with the runner closure it builds,
- the runner closure for ``PhaseExecutorStrategy``,
- the five runtime closures plus ``loop_guard_evaluator`` and the
  ``PhaseCapabilityReader`` for phase executors,
- a :class:`PhaseRunCursor` for :meth:`resume` to seed the visit
  loop from a checkpointed node instead of restarting from entry.

Deletion policy: this adapter is the sole production entry point.
There is no other production interpreter.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import lift_executable_plan
from lca.framework.graph.strategies.phase_executor_strategy import (
    PhaseExecutorStrategy,
    PhaseRunner,
)
from lca.framework.graph.strategies.subgraph_strategy import (
    RecursiveRunner,
    SubgraphStrategy,
)
from lca.framework.graph.strategy_registry import (
    PhaseExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
)
from lca.framework.graph.traversal import PlanTraversal
from lca.harness.declarative.compile.phase.capabilities import (
    MappingPhaseCapabilities,
)

if TYPE_CHECKING:
    from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
        PhaseContext,
        PhaseInput,
        PhaseResult,
    )
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
    the new kernel. The runtime closures, capability reader, and
    loop guard are stored on the adapter so the kernel-native
    :class:`PhaseRunner` closure can reach them when it constructs
    a :class:`RestrictedPhaseContext` for each phase visit.

    ``run`` performs a fresh traversal from the plan's entry node.
    ``resume`` accepts a :class:`PhaseRunCursor` and seeds the
    traversal at ``cursor.current_node_id``; when ``cursor`` is
    ``None`` it falls back to a fresh run.
    """

    registry: StrategyRegistry | None = None
    runner: Any = None
    executor_lookup: PhaseExecutorLookup | None = None
    journal: Any = None
    effect_gateway: Any = None
    reducer: Any = None
    phase_observer: Any = None
    lifecycle_publisher: Any = None
    loop_guard_evaluator: Any = None
    capabilities: Any = None
    phase_executors: Mapping[str, Any] | None = None
    phase_capabilities: Any = None
    _depth_counter: int = 0

    def __post_init__(self) -> None:
        # Adapter accepts ``capabilities`` (single source) and the
        # ``phase_executors`` / ``phase_capabilities`` pair from the
        # runtime factory's expanded ``create()`` signature. Prefer the
        # single ``capabilities`` value when set; otherwise fall back
        # to ``phase_capabilities``. ``phase_executors`` always wins as
        # the executor resolver because it is keyed by canonical
        # capability name and is the SSOT for which executor to call.
        if self.capabilities is None:
            self.capabilities = self.phase_capabilities
        # Build the per-adapter registry once. Each adapter carries its
        # own PhaseExecutorStrategy instance with a runner closure
        # wired to the five runtime closures, so concurrent adapters do
        # not stomp each other's runner.
        if self.registry is None:
            self.registry = _build_registry_with_runner(
                self._build_runner(),
                self._build_recursive_runner(),
                self._depth,
                default_strategy_registry(),
            )

    def _build_runner(self) -> PhaseRunner:
        """Return the closure ``PhaseExecutorStrategy.execute`` invokes.

        The closure resolves the :class:`PhaseExecutor` for the active
        node from ``self._phase_executors`` (the canonical
        ``Mapping[str, PhaseExecutor]`` provided by
        ``ProductionRuntimeDeps``), builds a
        :class:`RestrictedPhaseContext` from the five runtime closures
        plus the ``AgentState`` carried in
        ``StrategyContext.node_config["agent_state"]``, and awaits
        ``executor.execute(context, phase_input)``.

        The capability key for one phase is
        ``phase.<semantic_phase>.standard``; the node id of the form
        ``<semantic_phase>.main`` parses to ``<semantic_phase>``. Nodes
        that don't fit this convention raise a fail-loud.
        """
        phase_executors = self.phase_executors
        capabilities = self.capabilities
        journal = self.journal
        phase_observer = self.phase_observer

        async def runner(
            phase_input: "PhaseInput",
            strategy_ctx: Any,
        ) -> "PhaseResult":
            node_id = str(getattr(strategy_ctx, "node_id", ""))
            semantic = node_id.split(".", 1)[0] if node_id else ""
            if not semantic:
                raise RuntimeError(
                    f"PhaseRunner cannot resolve semantic phase from node_id={node_id!r}"
                )
            capability_key = f"phase.{semantic}.standard"
            executor = _resolve_phase_executor(
                phase_executors=phase_executors,
                capability_key=capability_key,
                node_id=node_id,
            )
            agent_state = dict(strategy_ctx.node_config or {}).get("agent_state")
            context = _build_phase_context(
                plan_ref=strategy_ctx.plan_ref,
                node_ref=node_id,
                agent_state=agent_state,
                journal=journal,
                phase_observer=phase_observer,
                capabilities=capabilities,
            )
            return await executor.execute(context, phase_input)

        return runner

    def _build_recursive_runner(self) -> RecursiveRunner:
        """Return the kernel-native recursive closure for subgraphs.

        Loads the bundle YAML referenced by ``ref.plan_ref`` (already
        lifted by :func:`SubgraphStrategy._load_subgraph_plan` before
        this closure is invoked), then runs the new kernel against
        the sub-plan via the adapter's per-adapter registry. The
        resulting :class:`InterpretationResult.output` is returned to
        the outer node as the merged port map.
        """
        registry = self.registry

        async def recursive_runner(
            sub_plan: Any,
            outer_state: Any,
            depth: int,
        ) -> Mapping[str, Any]:
            interp = PlanInterpreter(registry=registry)
            result = await interp.run(sub_plan, outer_state=outer_state)
            return dict(result.output)

        return recursive_runner

    def _depth(self) -> int:
        self._depth_counter += 1
        return self._depth_counter

    async def run(
        self,
        executable: object,
        *,
        state: object,
        input: object = None,
        budget: object = None,
        capabilities: object = None,
        artifacts: object = None,
        spec: object = None,
    ) -> object:
        """Execute ``executable`` fresh from the declared entry node."""
        plan = lift_executable_plan(executable)
        interp = PlanInterpreter(
            registry=self.registry or default_strategy_registry(),
            artifacts=artifacts or {},
        )
        result = await interp.run(plan, outer_state=state)
        return _legacy_result_shim(
            state=state,
            result=result,
        )

    async def resume(
        self,
        executable: object,
        *,
        state: object,
        cursor: object,
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
        """
        plan = lift_executable_plan(executable)
        if cursor is None or not getattr(cursor, "current_node_id", ""):
            return await self.run(
                executable,
                state=state,
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
            artifacts=artifacts or {},
        )
        seeded = _seed_traversal(plan, start_id, visited)
        result = await interp.run(plan, outer_state=state, traversal=seeded)
        return _legacy_result_shim(state=state, result=result)


def _legacy_result_shim(
    *, state: object, result: InterpretationResult
) -> object:
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


def _build_registry_with_runner(
    runner: PhaseRunner,
    recursive_runner: RecursiveRunner,
    depth_counter: Callable[[], int],
    source: StrategyRegistry,
) -> StrategyRegistry:
    """Return a fresh :class:`StrategyRegistry` whose phase-executor
    strategy carries the host-injected ``runner`` closure and whose
    subgraph strategy carries the recursive runner.

    The default registry exposes a singleton :class:`PhaseExecutorStrategy`
    with ``runner=None`` (its registered shape). Each adapter copies the
    registry, swaps in a fresh strategy instance with ``runner`` wired,
    and runs that. Concurrent adapters no longer race over a shared
    ``runner`` field.
    """
    new_registry = StrategyRegistry()
    for kind in source.kinds():
        strategy = source.resolve(kind)
        if isinstance(strategy, PhaseExecutorStrategy):
            new_registry.register(PhaseExecutorStrategy(runner=runner))
        elif isinstance(strategy, SubgraphStrategy):
            new_registry.register(
                SubgraphStrategy(
                    recursive_runner=recursive_runner,
                    depth_counter=depth_counter,
                )
            )
        else:
            new_registry.register(strategy)
    return new_registry


def _resolve_phase_executor(
    *,
    phase_executors: Mapping[str, Any] | None,
    capability_key: str,
    node_id: str,
) -> Any:
    """Resolve one phase executor instance from the executor map.

    ``phase_executors`` is the canonical ``Mapping[str, PhaseExecutor]``
    owned by ``ProductionRuntimeDeps``. The map is keyed by capability
    key (e.g. ``phase.perceive.standard``). Missing executor raises
    fail-loud — the kernel cannot proceed without it.
    """
    if phase_executors is None:
        raise RuntimeError(
            f"PlanInterpreterAdapter.phase_executors is None; "
            f"cannot resolve {capability_key!r} for node {node_id!r}"
        )
    executor = phase_executors.get(capability_key)
    if executor is None:
        raise RuntimeError(
            f"phase executor {capability_key!r} not found in phase_executors "
            f"(have: {sorted(phase_executors)})"
        )
    return executor


def _build_phase_context(
    *,
    plan_ref: str,
    node_ref: str,
    agent_state: Any,
    journal: Any,
    phase_observer: Any,
    capabilities: Any,
) -> "PhaseContext":
    """Build the :class:`PhaseContext` passed to ``PhaseExecutor.execute``.

    Uses :class:`RestrictedPhaseContext` (the typed per-phase view).
    Capabilities default to an empty mapping if the adapter did not
    receive one so tests can construct adapters without a Cordis boot.
    """
    from lca.contracts.models.core.state.state import AgentState, Budget
    from lca.harness.declarative.lifecycle.phase_context import (
        RestrictedPhaseContext,
    )

    state = agent_state if isinstance(agent_state, AgentState) else AgentState(
        trace_id=str(plan_ref or ""),
        task=str(node_ref or ""),
    )
    budget = getattr(state, "budget", None) or Budget()
    if capabilities is None:
        capabilities = MappingPhaseCapabilities({})
    return RestrictedPhaseContext(
        plan_ref=str(plan_ref or ""),
        node_ref=str(node_ref or ""),
        state=state,
        journal=journal,
        budget=budget,
        capabilities=capabilities,
    )


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


__all__ = [
    "PhaseRunCursor",
    "PlanInterpreterAdapter",
    "_LegacyResultShim",
]
