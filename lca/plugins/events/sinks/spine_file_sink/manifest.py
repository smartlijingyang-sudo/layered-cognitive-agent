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
    """SpineFileSink boot — Session.observe 优先；boot 缺席走 mount_sink COMPAT。

    Session 在场时只经
    :func:`lca.plugins.events._session_observe.register_as_session_observer`
    注册。plugin boot 时 ``current_session`` 通常为空（run bind 才
    ``set_session``），此时 ``EventBus.mount_sink`` 挂
    :class:`lca_kernel.events.sinks.SinkBackend`，由
    :meth:`~lca_kernel.events.bus.EventBus._dispatch_sinks` 派发落盘。
    """
    from lca.plugins.events._session_observe import register_as_session_observer

    sink = SpineFileSink()
    if register_as_session_observer(SINK_PLUGIN_CLASS, sink):
        ctx.provide("event.sink.spine_file", sink)
        return

    # COMPAT(delete-when: rg "mount_sink" lca/plugins/events/sinks = 0,
    #   tracking: ADR-0186 PR-3f)
    # Boot 时 Session 未 set；生产靠 EventBus 双写投递。删条件：run bind
    # 经 Session.observe 挂上本 sink，且 observe 派发带原 payload；
    # profile 以 JsonlSessionPersistence 为 spine.jsonl 唯一写方。
    from lca_kernel.events.bus import EventBus
    from lca_kernel.events.hooks import FailureSemantics

    bus_obj = ctx.soft_get("event.bus") or EventBus.default()
    if not isinstance(bus_obj, EventBus):
        msg = "event.sink.spine_file boot 失败：event.bus 未装载"
        raise RuntimeError(msg)
    bus_obj.mount_sink(
        sink_id="lca.events.sink.spine_file",
        backend=sink,
        failure=FailureSemantics.FAIL_FAST,
    )
    ctx.provide("event.sink.spine_file", sink)


__all__ = ["SINK_PLUGIN_CLASS", "setup"]
