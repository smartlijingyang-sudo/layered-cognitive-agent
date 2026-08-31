"""EventDescriptorRegistry seam plugin (Tier-1) —— ADR-0063 PR-7.

声明 ``event_descriptor_registry`` 服务形状。boot 后 ``providers/event_descriptor``
会把 49 个内置 ``EventDescriptor`` 灌进注册中心；插件也可继续 ``register()``
追加自定义事件类型。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.event_descriptor_registry import EventDescriptorRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-event-descriptor-registry",
    provides=["event_descriptor_registry"],
    implements=[EventDescriptorRegistry],
    layer="L0",
    effects="none",
    description="Provide the EventDescriptorRegistry service (PR-7 source inversion).",
    test_suite="tests/test_event_descriptor_registry.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-event-descriptor-registry.checked', 'lca-event-descriptor-registry.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('event_descriptor_registry',),
        emits=('event_descriptor_registry.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import InMemoryEventDescriptorRegistry

    ctx.provide("event_descriptor_registry", InMemoryEventDescriptorRegistry())
