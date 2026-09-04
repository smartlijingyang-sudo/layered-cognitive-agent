"""Journal sink plugin Manifest（ADR-0180 / ADR-0183 PR-7）。

统一目录：``lca/plugins/events/sinks/<sink_name>/manifest.py``。
sinks / publishers / subscribers 在 :mod:`lca_kernel.events.config` SSOT 中按
plugin id 鉴权。
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
from lca.plugins.events.sinks.journal.sink import JournalSink

# sink 的 plugin class（必须在 yaml subscribers 全路径登记）。
SINK_PLUGIN_CLASS = JournalSink


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.events.sink.journal",
    provides=["event.sink.journal"],
    requires=[],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Journal sink（ADR-0180 / ADR-0183 PR-7）：缓存 EventRecord，订阅 EventBus 所有 category。"
    ),
    test_suite="tests/plugins/events/sinks/test_journal.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.sink.consume",)),
        observability=EvidenceContract(descriptors=("event.sink.journal.written",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(),
        state_mutation="forbidden",
    ),
    marker_class=JournalSink,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """Journal sink boot — Session.observe 优先；缺席回退订阅。

    PR-3f-sample：sink 优先经
    :func:`lca.plugins.events._session_observe.register_as_session_observer`
    注册到 Session 观察面；Session 未装载时按 yaml 白名单逐条
    ``bus.subscribe`` 接线（marker class 已在 catalog，
    ``lca.application.spawn`` 路径下 JournalSink 可被 discover）。
    """
    from lca.plugins.events._session_observe import register_as_session_observer
    from lca_kernel.events.bus import EventBus

    sink = JournalSink()
    if register_as_session_observer(SINK_PLUGIN_CLASS, sink.on_event):
        ctx.provide("event.sink.journal", sink)
        return

    # COMPAT(delete-when: Session.observe 机制落地且 journal sink 全迁，本文件
    # rg "bus_obj.subscribe" = 0；tracking: ADR-0183 后续 PR-3f-sample)
    bus_obj = ctx.soft_get("event.bus") or EventBus.default()
    if not isinstance(bus_obj, EventBus):
        # PR-5：bus 缺位时不抛（profile resolve 完成前 event.bus 可能未到位），
        # 改由 :meth:`EventRegistry.refresh` 后的实际 bus 自动 subscribe。
        return
    for spec in bus_obj.registry.specs:
        bus_obj.subscribe(
            plugin=SINK_PLUGIN_CLASS,
            category=spec.category,
            on_event=sink.on_event,
        )
    ctx.provide("event.sink.journal", sink)


__all__ = ["SINK_PLUGIN_CLASS"]
