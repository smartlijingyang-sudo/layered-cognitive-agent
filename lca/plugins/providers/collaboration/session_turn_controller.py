"""Profile provider for session-scoped Agent-turn task ownership."""

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
from lca.contracts.protocols.session.session_turn import SessionTurnControllerFactory
from lca.harness.agent.turn_controller import InProcessSessionTurnController
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Default in-process Session turn controller configuration."""

    model_config = {"extra": "forbid"}


class InProcessSessionTurnControllerFactory(SessionTurnControllerFactory):
    """Create one cancellation-aware task controller for each live Session."""

    def create(self, *, session_id: str) -> InProcessSessionTurnController:
        return InProcessSessionTurnController(session_id=session_id)


@plugin(
    id="lca-session-turn-controller-factory",
    requires=[],
    provides=["session_turn_controller_factory"],
    implements=[SessionTurnControllerFactory],
    layer="L3",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide isolated session-turn task ownership so a Profile may replace "
        "cancellation and serialization behavior without changing a loop or carrier."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-session-turn-controller-factory.checked",
                "lca-session-turn-controller-factory.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("session_turn_controller_factory",),
        emits=("session_turn_controller_factory.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    """Expose the default in-process controller factory to the booted Profile."""

    del config
    ctx.provide("session_turn_controller_factory", InProcessSessionTurnControllerFactory())


__all__ = ["Config", "InProcessSessionTurnControllerFactory", "setup"]
