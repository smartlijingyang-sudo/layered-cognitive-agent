"""Console projector subscriber plugin Manifest（ADR-0180 / ADR-0183 PR-7）。

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

# subscriber 的 plugin class（必须在 yaml subscribers全路径登记）。
SUBSCRIBER_PLUGIN_CLASS = ConsoleProjectorSubscriber


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.events.subscriber.console_projector",
    provides=["event.subscriber.console_projector"],
    requires=[],
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
        reads=("event.bus",),
        emits=(),
        state_mutation="forbidden",
    ),
    marker_class=ConsoleProjectorSubscriber,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """Console projector subscriber boot — Session.observe 优先；缺席回退订阅。

    PR-3f-sample:observer 优先经
    :func:`lca.plugins.events._session_observe.register_as_session_observer`
    注册到 Session 观察面;Session 未装载时回退按 yaml 白名单逐条
    ``bus.subscribe``(marker class 已在 catalog,``lca.application.spawn``
    路径下 ConsoleProjectorSubscriber 可被 discover)。
    """
    from lca.plugins.events._session_observe import register_as_session_observer
    from lca_kernel.events.bus import EventBus

    subscriber = ConsoleProjectorSubscriber()
    if register_as_session_observer(SUBSCRIBER_PLUGIN_CLASS, subscriber.on_event):
        ctx.provide("event.subscriber.console_projector", subscriber)
        return

    # COMPAT(delete-when: Session.observe 机制落地且 console projector 全迁,本文件
    # rg "bus_obj.subscribe" = 0;tracking: ADR-0183 后续 PR-3f-sample)
    bus_obj = ctx.soft_get("event.bus") or EventBus.default()
    if not isinstance(bus_obj, EventBus):
        return
    for spec in bus_obj.registry.specs:
        bus_obj.subscribe(
            plugin=SUBSCRIBER_PLUGIN_CLASS,
            category=spec.category,
            on_event=subscriber.on_event,
        )
    ctx.provide("event.subscriber.console_projector", subscriber)


__all__ = ["SUBSCRIBER_PLUGIN_CLASS"]
