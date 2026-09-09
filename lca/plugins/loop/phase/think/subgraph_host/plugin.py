"""Think phase host that runs the think subgraph bundle with parity to standard."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

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
    CapabilityDeclaration,
    ContributionRole,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
    VerificationDeclaration,
)
from lca.harness.graph.execute.subgraph_phase_runner import (
    SUBGRAPH_PHASE_RUNNER_CAPABILITY,
    SubgraphPhaseRunner,
    default_subgraph_phase_runner,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class SubgraphHostConfig(BaseModel):
    """Configuration for the think subgraph host executor."""

    model_config = {"extra": "forbid"}

    plan_ref: str = Field(default="bundles/think-subgraph.yaml")
    entry_node: str = Field(default="think.subgraph.shortcut")


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="phase.think.subgraph_host",
    revision="1.0.0",
    kind=PluginSpecKind.PHASE_EXECUTOR,
    layer="L2",
    functional_group="cognitive-phase",
    implementation=PluginImplementation(
        module="lca.plugins.loop.phase.think.subgraph_host.plugin",
        setup="setup",
        factory="create_executor",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.loop.phase.think.subgraph_host.plugin.SubgraphHostConfig"
    ),
    provides=(
        CapabilityDeclaration(
            key="phase.think.subgraph_host",
            cardinality="one",
            protocol="PhaseExecutor",
            scope="run",
        ),
    ),
    requires=(),
    effects=("none",),
    ownership=OwnershipDeclaration(
        reads=(
            "state.view",
            "journal.cursor",
            SUBGRAPH_PHASE_RUNNER_CAPABILITY,
        ),
        emits=("phase.think.result",),
        state_mutation="forbidden",
    ),
    lifecycle=LifecycleDeclaration(scopes=("run",), activation="true", disposal="required"),
    relations=(),
    evidence=EvidenceDeclaration(emits=("PhaseThinkCompleted",), replay="required"),
    verification=VerificationDeclaration(
        test_suite="tests/cognition/test_think_subgraph_parity.py",
        properties=("phase_result_contract", "no_state_mutation"),
    ),
    contributes=(
        PhaseContribution(
            phase=SemanticPhase.THINK,
            role=ContributionRole.FINALIZE,
            executor="phase.think.subgraph_host",
            output="phase.think.result",
            order=0,
        ),
    ),
)


def _runner_for(context: PhaseContext) -> SubgraphPhaseRunner:
    runner = context.capabilities.get(SUBGRAPH_PHASE_RUNNER_CAPABILITY)
    if isinstance(runner, SubgraphPhaseRunner):
        return runner
    return default_subgraph_phase_runner()


@dataclass(frozen=True, slots=True)
class SubgraphHostThinkExecutor:
    """Run the configured think subgraph and surface its terminal ``PhaseResult``."""

    plan_ref: str
    entry_node: str

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        runner = _runner_for(context)
        return await runner.run_terminal_subgraph(
            plan_ref=self.plan_ref,
            entry_node=self.entry_node,
            context=context,
            input=input,
        )


@plugin(
    id="phase.think.subgraph_host",
    Config=SubgraphHostConfig,
    provides=("phase.think.subgraph_host",),
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
            descriptors=("phase_think_subgraph_host.checked", "phase_think_subgraph_host.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", SUBGRAPH_PHASE_RUNNER_CAPABILITY),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: SubgraphHostConfig) -> None:
    ctx.provide(
        "phase.think.subgraph_host",
        SubgraphHostThinkExecutor(
            plan_ref=config.plan_ref,
            entry_node=config.entry_node,
        ),
    )


def create_executor(
    *,
    plan_ref: str = "bundles/think-subgraph.yaml",
    entry_node: str = "think.subgraph.shortcut",
) -> SubgraphHostThinkExecutor:
    return SubgraphHostThinkExecutor(plan_ref=plan_ref, entry_node=entry_node)


__all__ = ["SubgraphHostConfig", "SubgraphHostThinkExecutor", "create_executor", "setup"]
