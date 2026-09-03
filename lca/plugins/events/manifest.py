"""事件 v2 插件 Manifest（ADR-0179）。

两个插件：

- ``lca.events.sender`` (provider) —— 唯一事件发送者。``provides=["events.sender"]``，
  ``requires=["events.consumer_registry"]``。
- ``lca.events.consumer.console_projector`` (sink) —— 试点控制台投影消费者。
  ``provides=["events.consumer.console_projector"]``，
  ``requires=["events.sender"]``（试点期不强依赖 sender 对象本身，仅声明）。

Manifest 字段沿用 :mod:`lca.contracts.protocols.declarative.declarative_plugin`
的字面 schema；本模块不重写声明。
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

# ── lca.events.sender ──────────────────────────────────────────────────────


class _SenderConfig(BaseModel):
    model_config = {"extra": "forbid"}
    dual_write_legacy: bool = True


@plugin(
    id="lca.events.sender",
    provides=["events.sender"],
    requires=["events.consumer_registry"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "事件 v2 唯一发送者；接收 typed Event，委托 EventRouterImpl 派发给订阅者。"
        "试点期双写到旧 journal backend（COMPAT，删除条件见 ADR-0179）。"
    ),
    test_suite="tests/plugins/events/test_sender_publish.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_OBSERVABILITY,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("events.publish",)),
        observability=EvidenceContract(
            descriptors=("events.sender.published", "events.sender.dual_write")
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("events.consumer_registry",),
        emits=("events.sender.published",),
        state_mutation="forbidden",
    ),
)
async def setup_sender(ctx: PluginContext, config: _SenderConfig) -> None:
    from lca.plugins.events.consumer_registry import ConsumerRegistry
    from lca.plugins.events.router import EventRouterImpl
    from lca.plugins.events.sender import EventSenderImpl

    registry = (
        ctx.resolve("events.consumer_registry")
        if hasattr(ctx, "resolve")
        else ctx.get("events.consumer_registry")
    )  # type: ignore[attr-defined]
    if not isinstance(registry, ConsumerRegistry):
        # 试点：ctx API 不一致时退化为裸构造（profile 未配齐时的安全 fallback）。
        registry = ConsumerRegistry()
    router = EventRouterImpl(registry)
    sender = EventSenderImpl(router, dual_write_legacy=config.dual_write_legacy)
    ctx.provide("events.sender", sender)


# ── lca.events.consumer.console_projector ─────────────────────────────────


class _ProjectorConfig(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.events.consumer.console_projector",
    provides=["events.consumer.console_projector"],
    requires=[],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "控制台投影消费者（试点）：订阅全量 EventCategory，按字段渲染。"
        "试点期仅覆盖 TEAM_DELEGATION / DelegationCacheHit。"
    ),
    test_suite="tests/plugins/events/test_consumer_subscription.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_OBSERVABILITY,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("events.consume",)),
        observability=EvidenceContract(descriptors=("events.consumer.console_projector.rendered",)),
    ),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("events.consumer.console_projector.rendered",),
        state_mutation="forbidden",
    ),
)
async def setup_console_projector(ctx: PluginContext, config: _ProjectorConfig) -> None:
    from lca.plugins.events.consumers.console_projector import ConsoleProjectorConsumer

    consumer = ConsoleProjectorConsumer()
    ctx.provide("events.consumer.console_projector", consumer)

    # 试点：如果 consumer_registry 已注册（sender 在更早阶段已 boot），把本消费者加入。
    registry_obj: object | None = None
    for attr_name in ("get", "resolve"):
        getter = getattr(ctx, attr_name, None)
        if not callable(getter):
            continue
        registry_obj = getter("events.consumer_registry")
        if registry_obj is not None:
            break
    if registry_obj is not None:
        from lca.plugins.events.consumer_registry import ConsumerRegistry

        if isinstance(registry_obj, ConsumerRegistry):
            registry_obj.register(consumer)
