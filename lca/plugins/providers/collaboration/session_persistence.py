"""Default Provider for the profile-selected durable Session fact stream."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.session.session_persistence import SessionPersistenceFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.harness.session.persistence import JsonlSessionPersistenceFactory


class Config(BaseModel):
    """Default session-persistence provider configuration."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-session-persistence-jsonl-provider",
    requires=[],
    provides=["session_persistence_factory"],
    implements=[SessionPersistenceFactory],
    layer="L0",
    effects="filesystem",
    kind=PluginKind.PROVIDER,
    description="Provide JSONL persistence for durable Session fact streams.",


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-session-persistence-jsonl-provider.checked', 'lca-session-persistence-jsonl-provider.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the default Session persistence factory."""

    del config
    ctx.provide("session_persistence_factory", JsonlSessionPersistenceFactory())


__all__ = ["Config", "setup"]
