"""publisher manifest（ADR-0180 @plugin 形式）。"""

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
from lca.plugins.events.sinks.spine_file_sink.sink import SpineFileSink

SINK_PLUGIN_CLASS = SpineFileSink


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.events.sink.spine_file",
    provides=["event.sink.spine_file"],
    requires=["event.bus"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "SpineFileSink（ADR-0181 PR-8 / ADR-0183 PR-7）：旧 spine FileSink 包装；"
        "EventBus callback 入口（failure=FAIL_FAST 落盘 fail-fast）；磁盘格式不变。"
    ),
    test_suite="tests.plugins.events.sinks.test_spine_file_sink",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.sink.consume",)),
        observability=EvidenceContract(descriptors=("event.sink.spine_file.written",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=("event.sink.spine_file.written",),
        state_mutation="forbidden",
    ),
)
async def setup_spine_file_sink(ctx: PluginContext, config: _Config) -> None:
    """SpineFileSink boot：构造 sink + 订阅 EventBus 所有 spine 类别。"""
    from lca_kernel.events.bus import EventBus
    from lca_kernel.events.hooks import FailureSemantics

    bus_obj = ctx.soft_get("event.bus")
    if not isinstance(bus_obj, EventBus):
        msg = "event.sink.spine_file boot 失败：event.bus 未装载"
        raise RuntimeError(msg)
    sink = SpineFileSink()
    for spec in bus_obj.registry.specs:
        if spec.category.value.startswith("spine."):
            bus_obj.subscribe(
                plugin=SINK_PLUGIN_CLASS,
                category=spec.category,
                on_event=sink,
                failure=FailureSemantics.FAIL_FAST,
            )
    ctx.provide("event.sink.spine_file", sink)


__all__ = ["SINK_PLUGIN_CLASS", "setup_spine_file_sink"]
