"""Observe-wildcard control contribution plugin (ADR-0074 Phase 3b).

Provides the ``control.observe.wildcard`` capability as an independent plugin,
enabling per-slot substitution without replacing the entire control surface.
This is the explicit no-op owner for the cross-cutting ``observe.*`` control slot.
"""

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
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class ObserveWildcardExecutor:
    """Explicit no-op owner for the cross-cutting ``observe.*`` control slot."""

    async def execute(self, _context: PhaseContext, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(result_kind="control", payload={"verdict": "allow"})


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.observe.wildcard",
    Config=Config,
    provides=["control.observe.wildcard"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.STOP,
            role=ContributionRole.OBSERVE,
            executor="control.observe.wildcard",
            output="observe.*",
            order=2,
        )
    ],
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("checkpoint.*",)),
        observability=EvidenceContract(descriptors=("control.observe.wildcard.checked",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("control.observe.wildcard",),
        emits=("control.observe.wildcard.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.observe.wildcard", ObserveWildcardExecutor())


__all__ = ["Config", "ObserveWildcardExecutor", "setup"]
