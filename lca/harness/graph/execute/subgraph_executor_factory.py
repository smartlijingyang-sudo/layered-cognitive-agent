"""Build ``ExecutablePlan`` instances for nested subgraph drives."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseExecutor,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.assembler.assembler import (
    ExecutablePlan,
    GraphAssembler,
    MappingRestrictedScope,
)
from lca.plugins.loop.phase.act.standard.plugin import create_executor as create_act_executor
from lca.plugins.loop.phase.perceive.standard.plugin import (
    create_executor as create_perceive_executor,
)
from lca.plugins.loop.phase.reflect.standard.plugin import (
    create_executor as create_reflect_executor,
)
from lca.plugins.loop.phase.remember.standard.plugin import (
    create_executor as create_remember_executor,
)
from lca.plugins.loop.phase.stop.standard.plugin import create_executor as create_stop_executor
from lca.plugins.loop.phase.think.standard.plugin import create_executor as create_think_executor
from lca.plugins.loop.phase.think.subgraph.classify.plugin import (
    create_executor as create_think_subgraph_classify_executor,
)
from lca.plugins.loop.phase.think.subgraph.gate.plugin import (
    create_executor as create_think_subgraph_gate_executor,
)
from lca.plugins.loop.phase.think.subgraph.reason.plugin import (
    create_executor as create_think_subgraph_reason_executor,
)
from lca.plugins.loop.phase.think.subgraph.route.plugin import (
    create_executor as create_think_subgraph_route_executor,
)
from lca.plugins.loop.phase.think.subgraph.shortcut.plugin import (
    create_executor as create_think_subgraph_shortcut_executor,
)

_PHASE_EXECUTOR_FACTORIES: dict[str, Callable[[], PhaseExecutor]] = {
    "phase.perceive.standard": create_perceive_executor,
    "phase.think.standard": create_think_executor,
    "phase.think.subgraph.shortcut": create_think_subgraph_shortcut_executor,
    "phase.think.subgraph.route": create_think_subgraph_route_executor,
    "phase.think.subgraph.reason": create_think_subgraph_reason_executor,
    "phase.think.subgraph.classify": create_think_subgraph_classify_executor,
    "phase.think.subgraph.gate": create_think_subgraph_gate_executor,
    "phase.act.standard": create_act_executor,
    "phase.reflect.standard": create_reflect_executor,
    "phase.remember.standard": create_remember_executor,
    "phase.stop.standard": create_stop_executor,
}


def executors_for_plan(plan: CompiledRunPlan) -> Mapping[str, PhaseExecutor]:
    """Materialize one executor instance per binding capability key in ``plan``."""

    executors: dict[str, PhaseExecutor] = {}
    for binding in plan.phase_bindings:
        capability = binding.executor_capability
        if capability in executors:
            continue
        factory = _PHASE_EXECUTOR_FACTORIES.get(capability)
        if factory is None:
            raise KeyError(f"no standard phase executor factory for {capability!r}")
        executors[capability] = factory()
        for contribution in binding.contributions:
            contribution_key = contribution.executor
            if contribution_key in executors:
                continue
            contribution_factory = _PHASE_EXECUTOR_FACTORIES.get(contribution_key)
            if contribution_factory is None:
                raise KeyError(
                    f"no standard phase executor factory for contribution {contribution_key!r}"
                )
            executors[contribution_key] = contribution_factory()
    return executors


def assemble_subgraph_executable(plan: CompiledRunPlan) -> ExecutablePlan:
    """Assemble one subgraph ``ExecutablePlan`` using standard phase executors."""

    scope = MappingRestrictedScope(executors_for_plan(plan))
    return GraphAssembler().assemble(plan, scope)


def default_subgraph_executable_factory() -> Callable[[CompiledRunPlan], ExecutablePlan]:
    """Return the default subgraph ``ExecutablePlan`` builder."""

    return assemble_subgraph_executable


__all__ = [
    "assemble_subgraph_executable",
    "default_subgraph_executable_factory",
    "executors_for_plan",
]
