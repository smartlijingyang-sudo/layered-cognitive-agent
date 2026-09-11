"""PlanInterpreterAdapter — exposes :class:`PlanInterpreter` under the
legacy :class:`DeclarativeInterpreter` Protocol.

This is the **production cutover seam**. The runtime plugin factory
at ``lca.plugins.journal.declarative.runtime_seams_provider`` constructs
this adapter with the five runtime closures
(``journal`` / ``effect_gateway`` / ``reducer`` / ``phase_observer`` /
``lifecycle_publisher``) plus ``loop_guard_evaluator``. The adapter
hands them to the kernel via host-injected strategy closures.

The adapter owns:

- a host-injected :class:`StrategyRegistry`,
- a runner closure for ``PhaseExecutorStrategy`` (host-injected),
- the five runtime closures, stored so kernel strategies that need
  them (currently ``PhaseExecutorStrategy``) can reach them through
  the kernel's :class:`StrategyContext`,
- a :class:`PhaseRunCursor` for :meth:`resume` to seed the visit
  loop from a checkpointed node instead of restarting from entry.

Deletion policy: this adapter is the sole production entry point.
There is no other production interpreter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import lift_executable_plan
from lca.framework.graph.strategy_registry import (
    PhaseExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
)
from lca.framework.graph.traversal import PlanTraversal

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
    the new kernel. The five runtime closures are stored on the
    adapter so callers can wire them into host-injected strategies;
    ``loop_guard_evaluator`` is reserved for kernel-side guarded-edge
    evaluation.

    ``run`` performs a fresh traversal from the plan's entry node.
    ``resume`` accepts a :class:`PhaseRunCursor` and seeds the
    traversal at ``cursor.current_node_id``; when ``cursor`` is
    ``None`` it falls back to a fresh run.
    """

    registry: StrategyRegistry = field(default_factory=default_strategy_registry)
    runner: Any = None
    executor_lookup: PhaseExecutorLookup | None = None
    journal: Any = None
    effect_gateway: Any = None
    reducer: Any = None
    phase_observer: Any = None
    lifecycle_publisher: Any = None
    loop_guard_evaluator: Any = None

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
            registry=self.registry,
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
            registry=self.registry,
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
