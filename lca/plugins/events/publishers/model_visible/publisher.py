"""model_visible publisher plugin（ADR-0185 §3.1 / PR-2）。

PR-2 目标:
- 把 ``spine.llm.request.header`` + ``spine.llm.request.header.assistant``
  两类 spine event 的**唯一授权 producer** plugin 化（I-MV-1）;
- 提供 :class:`ModelVisibleHook` 实例化与 LLM adapter 装饰器链挂钩能力
  （PR-3 真正装配,本 PR 仅 setup 时把 marker class 注入 ctx）;
- yaml 鉴权矩阵把 ``events.spine.reflector.body_llm`` 替换为
  ``events.model_visible.publisher``（同文件 bundle 行同步加）,
  强化 I-FW-BUS-1 / I-MV-1。

不动:

- fold 模块（PR-0 已合）;
- typed payload（PR-1 已合）;
- spine.yaml 非 publishers 字段。

ADR-0185 PR-4 收口后,旧 capture / LLM 装饰器路径全部删除,
本 plugin 装配为唯一 producer:

- plugin setup 实例化 :class:`ModelVisibleHook` 并注入
  ``llm.adapter.hook.model_visible``;composer ``instrument_llm`` 在
  LLM adapter 装饰器链用它包边界;
- yaml 鉴权把两类 category 的 producer 钉到本 plugin;旧 reflector 的
  ``emit_llm_call_*`` 类函数不触达这两类 category,无回归。
"""

from __future__ import annotations

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
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    get_current_cursor,
)

# Eager import 让 hook 模块的 module-level forward-ref rebuild 在 publisher
# import 时跑(测试 / 业务方直接调 SpineLlmRequestHeaderPayload 不再需要
# 先 model_rebuild)。
from lca.plugins.events.hooks.model_visible import (
    hook as _hook_module,  # noqa: F401  (import for side effect)
)
from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
    get_current_reasoner_prompt,
)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class ModelVisiblePublisher:
    """publisher plugin marker 类（I-MV-1 唯一授权 producer）。

    :class:`lca_kernel.events.registry.EventRegistry` 按
    ``id → marker_class`` 解析 yaml publishers token;本类即为 marker。

    业务方不直接调用;真正 publish 走 :class:`ModelVisibleHook` 内部
    ``bus.publish(payload, producer=ModelVisiblePublisher)``。
    """


@plugin(
    id="events.model_visible.publisher",
    provides=[
        "event.bus.publisher.model_visible",
        "llm.adapter.hook.model_visible",
    ],
    requires=["event.bus"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "model-visible publisher（ADR-0185 §3.1 / PR-2）：spine.llm.request.header "
        "+ spine.llm.request.header.assistant 两类 spine event 唯一授权 producer; "
        "ModelVisibleHook 内部 fold 优化 + canonicalHeader 归一 + EventBus 投递。"
    ),
    test_suite="tests/plugins/events/publishers/model_visible/test_publisher.py",
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.publisher.model_visible.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.llm.request.header",
            "spine.llm.request.header.assistant",
        ),
        state_mutation="forbidden",
    ),
    marker_class=ModelVisiblePublisher,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """model_visible publisher boot:注册 marker + 实例化 hook。

    做两件事:

    1. ``ctx.provide("event.bus.publisher.model_visible", ModelVisiblePublisher)``
       —— yaml 鉴权矩阵按 id 解析到 marker,生产者 publish 时通过
       ``producer=ModelVisiblePublisher`` 鉴权通过。
    2. 实例化 :class:`ModelVisibleHook` 并注入 ctx(键 ``llm.adapter.hook.model_visible``);
       composer ``instrument_llm(llm, ctx=...)`` 软查该键,把
       :class:`ModelVisibleHookAdapter` 挂到 LLM adapter 装饰器链最外层。
    """
    from lca_kernel.events.bus import EventBus

    ctx.provide("event.bus.publisher.model_visible", ModelVisiblePublisher)

    # 实例化 hook 并 provide 给 composer 装配。EventBus.default() 走进程单例;
    # 测试可注入 EventBus mock。
    bus: Any = EventBus.default()
    hook = _build_hook(bus=bus)
    ctx.provide("llm.adapter.hook.model_visible", hook)


def _build_hook(*, bus: Any) -> Any:
    """构造 :class:`ModelVisibleHook`(函数内 lazy import 避免环)。

    显式函数包裹为 setup 顶层留一行表达意图;内部 lazy import
    ModelVisibleHook 与 marker 类的相对位置打破。
    """
    from lca.plugins.events.hooks.model_visible.hook import ModelVisibleHook

    return ModelVisibleHook(
        bus=bus,
        cursor_provider=get_current_cursor,
        prompt_ctx_getter=get_current_reasoner_prompt,
    )


__all__ = ["ModelVisiblePublisher", "setup"]
