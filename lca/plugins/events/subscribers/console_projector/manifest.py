"""Console projector subscriber plugin Manifest（ADR-0180）。

统一目录：``lca/plugins/events/subscribers/<name>/manifest.py``。
"""

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
from lca.plugins.events.subscribers.console_projector.subscriber import (
    ConsoleProjectorSubscriber,
)
from lca_kernel.events import EventMechanism

# subscriber 的 plugin class（必须在 yaml subscribers 全路径登记）。
SUBSCRIBER_PLUGIN_CLASS = ConsoleProjectorSubscriber


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.events.subscriber.console_projector",
    provides=["event.subscriber.console_projector"],
    requires=["event.mechanism"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="控制台投影 subscriber（试点）：订阅 yaml 中声明的 category 渲染到 stdout。",
    test_suite="tests/plugins/events/subscribers/test_console_projector.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.subscriber.consume",)),
        observability=EvidenceContract(
            descriptors=("event.subscriber.console_projector.rendered",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.mechanism",),
        emits=("event.subscriber.console_projector.rendered",),
        state_mutation="forbidden",
    ),
)
async def setup_console_projector(ctx: PluginContext, config: _Config) -> None:
    """Console projector subscriber boot：构造 subscriber + 订阅 yaml 中所有 category。"""
    mechanism_obj = ctx.soft_get("event.mechanism")
    if not isinstance(mechanism_obj, EventMechanism):
        msg = "event.subscriber.console_projector boot 失败：event.mechanism 未装载"
        raise RuntimeError(msg)
    subscriber = ConsoleProjectorSubscriber()
    for spec in mechanism_obj.registry.specs:
        mechanism_obj.subscribe(
            plugin=SUBSCRIBER_PLUGIN_CLASS,
            category=spec.category,
            callback=subscriber.on_event,
        )
    ctx.provide("event.subscriber.console_projector", subscriber)


__all__ = ["SUBSCRIBER_PLUGIN_CLASS"]
