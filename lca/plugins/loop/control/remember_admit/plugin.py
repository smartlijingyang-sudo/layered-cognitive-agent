"""Remember-admit control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class RememberAdmitExecutor:
    """Execute remember-admit control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate remember-admit control."""
        if context.observation is None or context.reflection is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="memory admission requires outcome and reflection",
                    plugin_id="control.executor.remember-admit",
                ),
            )
        if context.state.status != TaskStatus.WORKING:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="terminal run does not admit new memory",
                    plugin_id="control.executor.remember-admit",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="turn is admissible to memory",
                plugin_id="control.executor.remember-admit",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.remember.admit",
    Config=Config,
    provides=["control.remember.admit"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.REMEMBER,
            role=ContributionRole.GOVERN,
            executor="control.remember.admit",
            output="remember.admit",
            order=0,
            aggregation="deny-on-any-deny",
        )
    ],
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.REMEMBER_ADMIT,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("memory.write",)),
        observability=EvidenceContract(descriptors=("control.remember.admit.checked",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("control.remember.admit",),
        emits=("control.remember.admit.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.remember.admit", RememberAdmitExecutor())


__all__ = ["Config", "RememberAdmitExecutor", "setup"]
