"""phase.think.orchestrator — drives the think 5-step phase graph."""

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
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    CapabilityDeclaration,
    ContributionRole,
    EvidenceDeclaration,
    LifecycleDeclaration,
    PhaseContribution,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
    VerificationDeclaration,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    OwnershipDeclaration as PhaseOwnershipDeclaration,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.graph.execute.subgraph_phase_runner import (
    SUBGRAPH_PHASE_RUNNER_CAPABILITY,
    SubgraphPhaseRunner,
    default_subgraph_phase_runner,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class OrchestratorConfig(BaseModel):
    """Configuration for the think orchestrator."""

    model_config = {"extra": "forbid"}

    plan_ref: str = Field(default="bundles/think-orchestrator.yaml")
    entry_node: str = Field(default="think.shortcut")


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="phase.think.orchestrator",
    revision="1.0.0",
    kind=PluginSpecKind.PHASE_EXECUTOR,
    layer="L2",
    functional_group="cognitive-phase",
    implementation=PluginImplementation(
        module="lca.plugins.loop.phase.think.orchestrator.plugin",
        setup="setup",
        factory="create_executor",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.loop.phase.think.orchestrator.plugin.OrchestratorConfig"
    ),
    provides=(
        CapabilityDeclaration(
            key="phase.think.orchestrator",
            cardinality="one",
            protocol="PhaseExecutor",
            scope="run",
        ),
    ),
    requires=(),
    effects=("none",),
    ownership=PhaseOwnershipDeclaration(
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
        test_suite="tests/think/test_orchestrator_graph.py",
        properties=("phase_result_contract", "no_state_mutation"),
    ),
    contributes=(
        PhaseContribution(
            phase=SemanticPhase.THINK,
            role=ContributionRole.FINALIZE,
            executor="phase.think.orchestrator",
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
class ThinkOrchestratorExecutor:
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
    id="phase.think.orchestrator",
    Config=OrchestratorConfig,
    provides=("phase.think.orchestrator",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_orchestrator_graph.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_orchestrator.checked",
                "phase_think_orchestrator.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", SUBGRAPH_PHASE_RUNNER_CAPABILITY),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: OrchestratorConfig) -> None:
    ctx.provide(
        "phase.think.orchestrator",
        ThinkOrchestratorExecutor(
            plan_ref=config.plan_ref,
            entry_node=config.entry_node,
        ),
    )


def create_executor(
    *,
    plan_ref: str = "bundles/think-orchestrator.yaml",
    entry_node: str = "think.shortcut",
) -> ThinkOrchestratorExecutor:
    return ThinkOrchestratorExecutor(plan_ref=plan_ref, entry_node=entry_node)


__all__ = ["OrchestratorConfig", "ThinkOrchestratorExecutor", "create_executor", "setup"]
