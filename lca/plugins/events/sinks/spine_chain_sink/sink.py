"""spine_chain_sink plugin 实现（ADR-0181 PR-2 复审）。

用 :mod:`lca_kernel.events.spine_runtime` 提取的 helpers：序列化 / chain
计算 / 时钟 / 落盘路径一律走 helpers，本 plugin 只负责"落盘"一件事。

PR-2 删-when：见 lca_kernel/events/spine_runtime.py 顶部说明。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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
from lca_kernel.events import EventRef
from lca_kernel.events.spine_runtime import (
    SpineChainContext,
    build_record,
    default_chain_path,
    is_spine_event,
)

log = logging.getLogger(__name__)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class SpineChainSink:
    """spine chain 落盘 sink（FD-1 fail-fast 由机制保证：抛错即上抛）。

    PR-2 复审：原 82 行实现收敛为 30 行（核心 = build record + append jsonl），
    chain / 时钟 / 路径 / 序列化全部走 spine_runtime helpers。
    """

    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path or default_chain_path()
        self._chain = SpineChainContext()

    def __call__(self, payload: Any, ref: EventRef) -> None:
        """sink callback（FD-1：抛错上抛 sender）。"""
        if not is_spine_event(payload):
            raise TypeError(f"SpineChainSink 只接 SpineEventPayload；got {type(payload).__name__}")
        # build_record = record 构造单一入口（ADR-0183 §3.5 PR-5）；
        # chain 显式传入时 prev_event_hash 取 chain.prev_hash，落盘字节不变。
        record = build_record(payload, ref, chain=self._chain)
        with self.output_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        if record.event_hash is not None:
            self._chain = SpineChainContext(prev_hash=record.event_hash)


@plugin(
    id="events.spine.chain_sink",
    provides=["event.bus.chain_sink"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "SpineChainSink（ADR-0181 PR-2）：spine chain 落盘 sink；"
        "EventBus callback 入口（fail-fast）。"
    ),
    test_suite="tests/plugins/events/sinks/test_spine_chain_sink.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.subscribe",)),
        observability=EvidenceContract(descriptors=("event.bus.chain_sink.written",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(),
        state_mutation="forbidden",
    ),
    marker_class=SpineChainSink,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_chain_sink boot — Session.observe 优先；缺席回退提供 marker。

    PR-3f-sample：sink 优先经
    :func:`lca.plugins.events._session_observe.register_as_session_observer`
    注册到 Session 观察面；Session 未装载时回退原 wire —— 验证
    ``event.bus`` 装载并提供 marker（yaml 鉴权按 marker class-path 物化进
    registry ``subscribers`` 映射，PR-6 收口前不重复 subscribe）。

    # COMPAT(delete-when: PR-6 鉴权三方一致, tracking: ADR-0183)
    # yaml consumer_rules 当前仍按类路径订阅；plugin 上线后逐步迁至
    # registry-based 订阅，PR-6 收口。setup 内部仅注册 marker + 提供 capability。
    """
    from lca.plugins.events._session_observe import register_as_session_observer
    from lca_kernel.events.bus import EventBus

    sink = SpineChainSink()
    if register_as_session_observer(SpineChainSink, sink):
        ctx.provide("event.bus.chain_sink", sink)
        return

    # COMPAT(delete-when: Session.observe 机制落地且 spine chain sink 全迁，本文件
    # rg "bus_obj" = 0；tracking: ADR-0183 后续 PR-3f-sample)
    bus_obj = ctx.soft_get("event.bus") or EventBus.default()
    if not isinstance(bus_obj, EventBus):
        msg = "event.bus.chain_sink boot 失败：event.bus 未装载"
        raise RuntimeError(msg)
    ctx.provide("event.bus.chain_sink", sink)


__all__ = ["SpineChainSink", "setup"]
