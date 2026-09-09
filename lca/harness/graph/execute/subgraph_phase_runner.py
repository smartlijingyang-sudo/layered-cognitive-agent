"""Drive a terminal subgraph plan from inside a ``PhaseExecutor`` host."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Final

from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphResolver,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
)
from lca.harness.declarative.compile.subgraph_resolver import default_subgraph_resolver
from lca.harness.declarative.lifecycle.phase_context import RestrictedPhaseContext
from lca.harness.graph.execute.subgraph_executor_factory import (
    default_subgraph_executable_factory,
    executors_for_plan,
)
from lca.harness.graph.predicate import evaluate_restricted_predicate

SUBGRAPH_PHASE_RUNNER_CAPABILITY: Final = "declarative.subgraph.phase_runner"


@dataclass(frozen=True, slots=True)
class SubgraphPhaseRunner:
    """Resolve and run one subgraph entry node for a phase host."""

    resolver: SubgraphResolver
    executable_factory: object

    async def run_terminal_subgraph(
        self,
        *,
        plan_ref: str,
        entry_node: str,
        context: PhaseContext,
        input: PhaseInput,
    ) -> PhaseResult:
        """Execute a subgraph plan and return its terminal ``PhaseResult``."""

        sub_plan = self.resolver.resolve(plan_ref)
        if sub_plan is None:
            raise RuntimeError(f"subgraph plan_ref could not be resolved: {plan_ref!r}")
        graph = sub_plan.phase_graph
        if graph is None:
            raise RuntimeError(f"subgraph {plan_ref!r} has no phase graph")
        if len(graph.nodes) <= 1:
            return await self._run_single_node(
                sub_plan=sub_plan,
                entry_node=entry_node,
                context=context,
                input=input,
            )
        factory = self.executable_factory
        executable = factory(sub_plan)
        return await self._drive_linear_subgraph(
            executable=executable,
            entry_node=entry_node,
            context=context,
            input=input,
        )

    async def _run_single_node(
        self,
        *,
        sub_plan: object,
        entry_node: str,
        context: PhaseContext,
        input: PhaseInput,
    ) -> PhaseResult:
        from lca.contracts.protocols.state.plan import CompiledRunPlan

        if not isinstance(sub_plan, CompiledRunPlan):
            raise RuntimeError("subgraph resolver returned non-plan value")
        binding = next(
            (item for item in sub_plan.phase_bindings if item.node_id == entry_node),
            None,
        )
        if binding is None:
            raise RuntimeError(f"subgraph has no phase binding for entry node {entry_node!r}")
        executors = executors_for_plan(sub_plan)
        executor = executors.get(binding.executor_capability)
        if executor is None:
            raise RuntimeError(
                f"subgraph missing executor for capability {binding.executor_capability!r}"
            )
        return await executor.execute(context, input)

    async def _drive_linear_subgraph(
        self,
        *,
        executable: object,
        entry_node: str,
        context: PhaseContext,
        input: PhaseInput,
    ) -> PhaseResult:
        from lca.harness.declarative.compile.assembler.assembler import ExecutablePlan

        if not isinstance(executable, ExecutablePlan):
            raise RuntimeError("subgraph executable factory returned non-executable plan")
        graph = executable.plan.phase_graph
        if graph is None:
            raise RuntimeError("subgraph executable has no phase graph")
        edges_by_source: dict[str, list[object]] = defaultdict(list)
        for edge in graph.edges:
            edges_by_source[edge.source].append(edge)

        artifacts = dict(context.artifacts)
        carry = ThinkSubgraphCarry(state=context.state)
        artifacts[CARRY_KEY] = carry
        current_id = entry_node
        phase_input = input

        while True:
            executable_node = executable.nodes.get(current_id)
            if executable_node is None:
                raise RuntimeError(f"subgraph node is not assembled: {current_id!r}")
            step_context = RestrictedPhaseContext(
                plan_ref=context.plan_ref,
                node_ref=current_id,
                state=carry.state,
                journal=context.journal,
                budget=context.budget,
                artifacts=artifacts,
                capabilities=context.capabilities,
                decision=context.decision,
                observation=context.observation,
                reflection=context.reflection,
                checkpoint_reason=context.checkpoint_reason,
            )
            result = await executable_node.executor.execute(step_context, phase_input)
            if result.result_kind == "decision":
                return result
            if isinstance(result.payload, ThinkSubgraphCarry):
                carry = result.payload
                artifacts[CARRY_KEY] = carry

            selected = None
            for edge in edges_by_source.get(current_id, ()):
                if evaluate_restricted_predicate(
                    edge.when,
                    result=result,
                    artifacts=artifacts,
                ):
                    selected = edge
                    break
            if selected is None:
                raise RuntimeError(f"subgraph has no matching edge from node {current_id!r}")
            current_id = selected.target
            phase_input = PhaseInput(
                artifact=result.payload,
                causation_refs=result.evidence_refs,
            )


def default_subgraph_phase_runner() -> SubgraphPhaseRunner:
    """Return a process-wide default runner for standard subgraph bundles."""

    return SubgraphPhaseRunner(
        resolver=default_subgraph_resolver(),
        executable_factory=default_subgraph_executable_factory(),
    )


__all__ = [
    "SUBGRAPH_PHASE_RUNNER_CAPABILITY",
    "SubgraphPhaseRunner",
    "default_subgraph_phase_runner",
]
