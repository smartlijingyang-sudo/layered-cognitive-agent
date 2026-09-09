"""think subgraph — skill route step."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig
from lca.plugins.loop.phase.think.subgraph._shared import run_route_step, step_plugin_spec

SPEC = step_plugin_spec(
    plugin_id="phase.think.subgraph.route",
    module="lca.plugins.loop.phase.think.subgraph.route.plugin",
)


@dataclass(frozen=True, slots=True)
class RouteStepExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        return await run_route_step(context, input)


@plugin(
    id="phase.think.subgraph.route",
    Config=StandardPhaseConfig,
    provides=("phase.think.subgraph.route",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/cognition/test_think_subgraph_parity.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_think_subgraph_route.checked", "phase_think_subgraph_route.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    del config
    ctx.provide("phase.think.subgraph.route", RouteStepExecutor())


def create_executor() -> RouteStepExecutor:
    return RouteStepExecutor()


__all__ = ["RouteStepExecutor", "create_executor", "setup"]
