"""Perceive group Definition — owns ctx.perceive (ADR-0056 / ADR-0061)."""

from __future__ import annotations

from pydantic import BaseModel

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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="perceive",
    provides=["perceive"],
    requires=[],
    layer="L1",
    kind=PluginKind.SEAM,
    effects="none",
    description="Perceive group registry; sensor plugins add() onto it.",
    test_suite="tests/test_composer_sensor_wiring.py",
    functional_group=FunctionalGroup.G4_PERCEPTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G4_PERCEPTION, control_slots=(ControlSlot.PERCEIVE_CONTEXT,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("perceive.contribute",)),
        observability=EvidenceContract(descriptors=("perceive.group.assembled",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("perceive",),
        emits=("perceive.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.perceive_service import PerceiveService

    ctx.provide("perceive", PerceiveService())
