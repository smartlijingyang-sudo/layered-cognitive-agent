"""Shared fixtures for declarative interpreter tests.

Subgraph stub resolver + factory let tests construct ``GenericPlanInterpreter``
without booting a full Cordis scope. After the ``PhaseEdge.subgraph_ref``
compile fix, every test using the ``web-standard.yaml`` plan needs these
stubs because the think edge now declares a subgraph reference.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from lca.contracts.models.core.state.state import Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    SemanticPhase as _SP,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_fault_tolerance import (
    PhaseExecutionPolicy,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    CognitivePhaseGraphPlan,
    PhaseBinding,
    PhaseNode,
    ValidationReport,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.assembler.assembler import (
    ExecutableNode,
    ExecutablePlan,
)


class _NoopSubgraphExecutor:
    """Minimal executor returning a terminal StopDecision."""

    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        from lca.contracts.models.core.policy.stop import StopDecision, StopReason

        return PhaseResult(
            result_kind="noop",
            payload=StopDecision(should_stop=True, reason=StopReason.TASK_COMPLETED),
        )


class StubSubgraphResolver:
    """Return a minimal CompiledRunPlan for any subgraph plan_ref."""

    def resolve(self, plan_ref: str) -> CompiledRunPlan | None:
        from lca.contracts.protocols.perceive.capability_plan import CapabilityPlan
        from lca.contracts.protocols.state.scope_plan import (
            BudgetCeiling,
            Scope,
            ScopePlan,
        )

        node = PhaseNode(
            id="subgraph.stub",
            semantic_phase=_SP.REFLECT,
            binding="phase.test.noop",
            max_visits=1,
            terminal=True,
            execution_policy=PhaseExecutionPolicy(),
        )
        graph = CognitivePhaseGraphPlan(entry=node.id, nodes=(node,), edges=())
        binding = PhaseBinding(
            node_id=node.id,
            semantic_phase=_SP.REFLECT,
            executor_capability="phase.test.noop",
            contributions=(),
        )
        cap_plan = CapabilityPlan(
            profile_path=f"sub://{plan_ref}",
            provider_bindings=(),
            relations=(),
        )
        scope_plan = ScopePlan(
            profile_path=f"sub://{plan_ref}",
            lifecycle=Scope.RUN,
            visibility=(Scope.RUN,),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        return CompiledRunPlan(
            profile_path=f"sub://{plan_ref}",
            capability=cap_plan,
            scope=scope_plan,
            phase_graph=graph,
            phase_bindings=(binding,),
            validation_report=ValidationReport(issues=()),
        )


def stub_subgraph_executable_factory(plan: CompiledRunPlan) -> ExecutablePlan:
    """Return a minimal ExecutablePlan for the stub subgraph plan."""
    nodes = {
        n.id: ExecutableNode(
            node_id=n.id,
            semantic_phase=n.semantic_phase,
            executor_capability="phase.test.noop",
            executor=_NoopSubgraphExecutor(),
            contributions=(),
            execution_policy=n.execution_policy,
        )
        for n in (plan.phase_graph.nodes if plan.phase_graph else ())
    }
    return ExecutablePlan(plan=plan, nodes=nodes)


@pytest.fixture
def stub_subgraph_resolver() -> StubSubgraphResolver:
    return StubSubgraphResolver()