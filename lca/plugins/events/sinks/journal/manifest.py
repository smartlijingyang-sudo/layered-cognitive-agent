"""Journal sink plugin Manifest（ADR-0180）。

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
from lca_kernel.events import EventMechanism

# sink 的 plugin class（必须在 yaml subscribers 全路径登记）。
SINK_PLUGIN_CLASS = JournalSink


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.events.sink.journal",
    provides=["event.sink.journal"],
    requires=["event.mechanism"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Journal sink（ADR-0180）：机制默认 sink；缓存 EventRecord，"
        "后续 PR 接 BoundObservability.journal 真正写盘。"
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
        reads=("event.mechanism",),
        emits=("event.sink.journal.written",),
        state_mutation="forbidden",
    ),
)
async def setup_journal_sink(ctx: PluginContext, config: _Config) -> None:
    """Journal sink boot：构造 sink + 订阅机制所有 category。"""
    mechanism_obj = ctx.soft_get("event.mechanism")
    if not isinstance(mechanism_obj, EventMechanism):
        msg = "event.sink.journal boot 失败：event.mechanism 未装载"
        raise RuntimeError(msg)
    sink = JournalSink()
    for spec in mechanism_obj.registry.specs:
        mechanism_obj.subscribe(
            plugin=SINK_PLUGIN_CLASS,
            category=spec.category,
            callback=sink.on_event,
        )
    ctx.provide("event.sink.journal", sink)


__all__ = ["SINK_PLUGIN_CLASS"]
