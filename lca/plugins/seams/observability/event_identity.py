"""EventIdentity seam plugin (Tier-1) —— ADR-0096 MVA-2 + ADR-0097.

声明 ``event_identities`` 注册中心；boot 后 ``providers/event_identity/stable_ulid``
注入 ``StableUlidIdentity`` 实现。新增 identity 策略 = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-event-identity-seam",
    provides=["event_identities"],
    requires=[],
    layer="L0",
    effects="none",
    description="Provide the event_identities registry (ADR-0096 MVA-2 + ADR-0097).",
    test_suite="tests/test_event_identity_seam.py::test_event_identity_seam_provides_registry",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-event-identity-seam.checked', 'lca-event-identity-seam.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('event_identities',),
        emits=('event_identities.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("event_identities", NamedRegistry())
