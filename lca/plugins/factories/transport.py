"""Transport Compose Service plugin — named factory ``transport.compose_service``.

Returns a fresh :class:`TransportService` per composition (per-compose
transport table; one per agent pipeline). Composer no longer instantiates
``TransportService()`` inline; it resolves a factory through this plugin.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.runtime.infra import TransportRegistryProtocol
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_transport_service_compose() -> TransportRegistryProtocol:
    from lca.infrastructure.capability.transport import TransportService

    return TransportService()


@plugin(
    id="transport.compose_service",
    provides=["transport.compose_service"],
    requires=[],
    implements=[TransportRegistryProtocol],
    layer="L1",
    effects="none",
    description="Compose-time TransportService factory (one fresh instance per compose).",
    test_suite="tests/test_plugin_alignment.py::test_compose_root_no_inline_instantiation",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('transport_compose_service.checked', 'transport_compose_service.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('transport.compose_service',),
        emits=('transport.compose_service.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the named factory ``transport.compose_service``."""
    ctx.provide("transport.compose_service", build_transport_service_compose)
