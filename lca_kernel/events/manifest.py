"""事件机制本体 Manifest（ADR-0180 D1）。

机制是 kernel 元层插件；**只有机制本体**在此注册。Sinks / publishers / subscribers
是普通业务 plugin，在 ``lca/plugins/events/{sinks,publishers,subscribers}/`` 各自
Manifest；机制 boot 时按 yaml SSOT 鉴权矩阵路由事件。
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
from lca_kernel.events.mechanism import _DEFAULT_CONFIG_DIR, EventMechanism
from lca_kernel.events.registry import EventRegistry


class _MechanismConfig(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.events.mechanism",
    provides=["event.mechanism"],
    requires=[],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "事件机制本体（ADR-0180）：kernel 元层；提供 send/subscribe 入口；"
        "按 lca_kernel/events/config/**/*.yaml 鉴权矩阵路由。"
    ),
    test_suite="tests/lca_kernel/events/test_mechanism_auth.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.send", "event.subscribe")),
        observability=EvidenceContract(descriptors=("event.mechanism.boot",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.config.ssot",),
        emits=("event.mechanism.boot",),
        state_mutation="forbidden",
    ),
)
async def setup_mechanism(ctx: PluginContext, config: _MechanismConfig) -> None:
    """机制 boot：构造 EventMechanism + 设为全局默认 + provide 给 ctx。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    mechanism = EventMechanism(registry)
    ctx.provide("event.mechanism", mechanism)
    # 进程级单例：业务方无 ctx 也能调 EventMechanism.default()（ADR-0180 D4）。
    EventMechanism.set_default(mechanism)
