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
    requires=[],
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
        emits=(),
        state_mutation="forbidden",
    ),
    marker_class=SINK_PLUGIN_CLASS,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """SpineFileSink boot — 只经 Session.observe 目录登记。

    :func:`lca.plugins.events._session_observe.register_as_session_observer`
    写入进程级目录；Session 在场立即挂上，boot 缺席则等 run bind
    ``set_session`` 整表挂上。不调用 ``mount_sink`` / ``bus.subscribe``。
    """
    from lca.plugins.events._session_observe import register_as_session_observer

    sink = SpineFileSink()
    register_as_session_observer(SINK_PLUGIN_CLASS, sink)
    ctx.provide("event.sink.spine_file", sink)


__all__ = ["SINK_PLUGIN_CLASS", "setup"]
