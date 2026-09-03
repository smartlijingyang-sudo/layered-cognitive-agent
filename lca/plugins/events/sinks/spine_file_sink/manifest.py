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
    requires=["event.mechanism"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "SpineFileSink（ADR-0181 PR-8）：旧 spine FileSink 包装；"
        "EventMechanism callback 入口；磁盘格式不变。"
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
        reads=("event.mechanism",),
        emits=("event.sink.spine_file.written",),
        state_mutation="forbidden",
    ),
)
async def setup_spine_file_sink(ctx: PluginContext, config: _Config) -> None:
    """SpineFileSink boot：构造 sink + 订阅机制所有 spine 类别。"""
    from lca_kernel.events import EventMechanism
    from lca_kernel.events.registry import EventRegistry

    mechanism_obj = ctx.soft_get("event.mechanism")
    if not isinstance(mechanism_obj, EventMechanism):
        msg = "event.sink.spine_file boot 失败：event.mechanism 未装载"
        raise RuntimeError(msg)
    sink = SpineFileSink()
    registry: EventRegistry = mechanism_obj.registry
    for spec in registry.specs:
        if spec.category.value.startswith("spine."):
            mechanism_obj.subscribe(
                plugin=SINK_PLUGIN_CLASS,
                category=spec.category,
                callback=sink,
            )
    ctx.provide("event.sink.spine_file", sink)


__all__ = ["SINK_PLUGIN_CLASS", "setup_spine_file_sink"]
