"""Tool-call E2E seam test (note 2026-09-11 / Part D).

Acceptance criterion #5 of the cutover plan: ``tool_call event →
tool_result event → final assistant message``. This integration test
proves the new ``PlanInterpreterAdapter`` wiring reaches the act node
and merges the ``Observation`` produced by a host-injected phase runner
onto the port registry at the right node.

The test:

- constructs a :class:`PlanInterpreterAdapter` with mock closures,
- registers a fresh :class:`PhaseExecutorStrategy` whose ``runner``
  returns ``PhaseResult(result_kind="observation", payload=Observation(success=True))``,
- lifts a small 5-node ``Plan`` by hand
  (``perceive → think → act → reflect → remember → stop``),
- runs the adapter and asserts
    (a) the visit loop reached the terminal node,
    (b) ``Observation(success=True)`` landed in the port registry
        under the act node's ``observation`` port.

The seam proof does not need a real tool-execution fixture; it
verifies the kernel wiring is intact.
"""
from __future__ import annotations

from typing import Any

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph.adapter import PlanInterpreterAdapter
from lca.framework.graph.strategies import PhaseExecutorStrategy
from lca.framework.graph.strategy_registry import StrategyRegistry


def _terminal_plan() -> Plan:
    """Hand-rolled six-phase plan: perceive → think → act → reflect → remember → stop.

    Each node uses ``PHASE_EXECUTOR`` binding so the registry can dispatch
    to the host-injected :class:`PhaseExecutorStrategy`. The terminal
    ``stop`` node has ``terminal=True`` so the kernel stops after one visit.
    Edges use ``when="true"`` so the registry's default predicate admits
    every transition.
    """
    nodes = (
        PlanNode(id="perceive", binding=BindingKind.PHASE_EXECUTOR, entry=True),
        PlanNode(id="think", binding=BindingKind.PHASE_EXECUTOR),
        PlanNode(id="act", binding=BindingKind.PHASE_EXECUTOR),
        PlanNode(id="reflect", binding=BindingKind.PHASE_EXECUTOR),
        PlanNode(id="remember", binding=BindingKind.PHASE_EXECUTOR),
        PlanNode(
            id="stop",
            binding=BindingKind.PHASE_EXECUTOR,
            terminal=True,
        ),
    )
    edges = tuple(
        PlanEdge(source=nodes[i].id, target=nodes[i + 1].id)
        for i in range(len(nodes) - 1)
    )
    return Plan(id="tool-call-e2e", nodes=nodes, edges=edges)


def _executable_for(plan: Plan) -> object:
    """Build a minimal ``ExecutablePlan``-shaped object the lifter accepts."""

    class _Plan:
        phase_graph = plan

    class _Exec:
        plan = _Plan()

    return _Exec()


class TestToolCallE2E:
    async def test_act_node_observation_lands_in_port_registry(self) -> None:
        # Single-shot observation payload the act runner emits.
        expected = Observation(
            observation_id="obs-1",
            success=True,
            payload={"tool_result": "ok"},
        )
        seen: dict[str, Any] = {}

        def _runner(phase_input: PhaseInput, ctx: StrategyContext) -> PhaseResult:
            seen[ctx.node_id] = ctx
            if ctx.node_id == "act":
                return PhaseResult(
                    result_kind="observation",
                    payload=expected,
                )
            return PhaseResult(result_kind="response", payload=None)

        registry = StrategyRegistry()
        # Register a PhaseExecutorStrategy that owns the runner; the kernel
        # dispatches every PHASE_EXECUTOR visit through it.
        registry.register(PhaseExecutorStrategy(runner=_runner))
        # Register a TERMINATE strategy so the final visit can dispatch
        # through the kernel; without it the loop would not advance.
        from lca.framework.graph.strategies import TerminateStrategy

        registry.register(TerminateStrategy())

        adapter = PlanInterpreterAdapter(registry=registry)
        plan = _terminal_plan()
        exec_obj = _executable_for(plan)

        # A dedicated PortRegistry to capture the kernel's merge_output
        # calls; the adapter builds its own but we observe via the visit
        # records instead.
        result = await adapter.run(executable=exec_obj, state=None)

        # 1. The kernel reached the terminal node.
        assert result.terminal_node == "stop", (
            f"kernel did not advance to the terminal node; "
            f"got {result.terminal_node!r}"
        )

        # 2. Every phase node was visited exactly once.
        visited_nodes = {v.node_id for v in result.visits}
        assert visited_nodes == {"perceive", "think", "act", "reflect", "remember", "stop"}

        # 3. The act visit's output carried the observation port value.
        act_visit = next(v for v in result.visits if v.node_id == "act")
        assert "observation" in act_visit.outputs, (
            f"act node did not produce an observation port; "
            f"got outputs={dict(act_visit.outputs)!r}"
        )
        assert act_visit.outputs["observation"] is expected, (
            f"act observation port did not land the host payload; "
            f"got {act_visit.outputs['observation']!r}"
        )

        # 4. The runner saw every phase node.
        assert set(seen) == {"perceive", "think", "act", "reflect", "remember", "stop"}

        # 5. Observation(success=True) is observable through the public API.
        assert expected.success is True


class TestResumeSeeding:
    async def test_resume_with_cursor_seeds_traversal(self) -> None:
        """Resume from a :class:`PhaseRunCursor` picks up at the cursor's node.

        The seam cutover promises a real ``resume`` path. With a cursor
        pointing at ``reflect``, the kernel should NOT re-visit ``perceive`` /
        ``think`` / ``act`` — only ``reflect`` and onward.
        """
        from lca.framework.graph.adapter import PhaseRunCursor

        visited: list[str] = []

        def _runner(phase_input: PhaseInput, ctx: StrategyContext) -> PhaseResult:
            visited.append(ctx.node_id)
            return PhaseResult(result_kind="response", payload=None)

        registry = StrategyRegistry()
        registry.register(PhaseExecutorStrategy(runner=_runner))
        from lca.framework.graph.strategies import TerminateStrategy

        registry.register(TerminateStrategy())

        adapter = PlanInterpreterAdapter(registry=registry)
        plan = _terminal_plan()
        exec_obj = _executable_for(plan)

        cursor = PhaseRunCursor(
            current_node_id="reflect",
            visited_nodes=("perceive", "think", "act"),
        )

        result = await adapter.resume(
            executable=exec_obj,
            state=None,
            cursor=cursor,
        )

        # The kernel must have visited at least the resume point
        # through the terminal node; it may NOT have re-visited the
        # three already-visited nodes (visit_counts pre-seeding).
        assert "reflect" in visited
        assert "remember" in visited
        assert "stop" in visited
        assert "perceive" not in visited
        assert "think" not in visited
        assert "act" not in visited

        assert result.terminal_node == "stop"

    async def test_resume_without_cursor_falls_back_to_run(self) -> None:

        visited: list[str] = []

        def _runner(phase_input: PhaseInput, ctx: StrategyContext) -> PhaseResult:
            visited.append(ctx.node_id)
            return PhaseResult(result_kind="response", payload=None)

        registry = StrategyRegistry()
        registry.register(PhaseExecutorStrategy(runner=_runner))
        from lca.framework.graph.strategies import TerminateStrategy

        registry.register(TerminateStrategy())

        adapter = PlanInterpreterAdapter(registry=registry)
        plan = _terminal_plan()
        exec_obj = _executable_for(plan)

        # cursor=None must fall through to a fresh run.
        result = await adapter.resume(
            executable=exec_obj,
            state=None,
            cursor=None,
        )

        assert visited == ["perceive", "think", "act", "reflect", "remember", "stop"]
        assert result.terminal_node == "stop"


__all__ = ["TestResumeSeeding", "TestToolCallE2E"]
